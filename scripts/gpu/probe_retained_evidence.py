"""Persist and read exact historical source pages in a disposable live-model probe."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.structura_api.main import create_app
from lib.auth.primitives import hash_secret
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.document_processing.models import ProcessingRun
from lib.document_processing.service import DocumentProcessingService
from lib.documents.access_policy import DocumentAccessContext
from lib.evidence.models import GenerationEvidenceManifest, GenerationEvidencePage
from lib.evidence.render_execution import retain_source_pages
from lib.evidence.write_service import RetainedEvidenceWriter
from scripts.gpu.probe_database import verify_isolated_database
from scripts.gpu.probe_persisted_parse import ProbeSource, write_private


def retain_and_replay(run: ProcessingRun, source: ProbeSource) -> dict[str, Any]:
    """The caller retains the exact parse job's renewing claim until this returns."""
    writer = RetainedEvidenceWriter(source.storage)
    attempts = []
    for _ in range(500):
        result = retain_source_pages(
            run.binding, storage=source.storage, service=writer, max_new_pages=1
        )
        attempts.append(asdict(result))
        if result.state == "sealed":
            break
        if result.new_pages != 1:
            raise RuntimeError("Retained evidence continuation made no bounded progress.")
    else:
        raise RuntimeError("Retained evidence did not seal within its page bound.")
    replay = retain_source_pages(run.binding, storage=source.storage, service=writer)
    if (
        replay.state != "sealed"
        or replay.new_pages
        or replay.new_bytes
        or replay.completion_sha256 != result.completion_sha256
        or replay.completed_page_ids != result.completed_page_ids
    ):
        raise RuntimeError("Retained source replay changed its sealed page inventory.")
    return {"attempts": attempts, "replay": asdict(replay)}


def verify_historical_api(
    run: ProcessingRun, source: ProbeSource, output_dir: Path
) -> dict[str, Any]:
    """Exercise real auth and routes through ASGI; no dependency overrides or public server."""
    settings = get_settings()
    verify_isolated_database(settings.database_url)
    if settings.derived_objects_root.resolve() != source.storage.roots["derived"].resolve():
        raise RuntimeError("API storage must resolve to this isolated probe's exact derived root.")
    token, token_id = _reader_token(source)
    base = (
        f"/api/v1/documents/{source.document_id}/parse-generations/"
        f"{run.binding.parse_generation_id}"
    )
    try:
        with TestClient(create_app()) as client:
            if client.get(base).status_code != 401:
                raise RuntimeError("Retained source metadata did not require authentication.")
            client.headers["X-API-Token"] = token
            before = _capture_pages(client, base)
            first = GenerationEvidenceManifest.model_validate(before["manifests"][0])
            _cancel_successor(source, first)
            after = _capture_pages(client, base)
            if before["pages"] != after["pages"] or before["renders"] != after["renders"]:
                raise RuntimeError("A later cancelled run changed historical source evidence.")
            if any(m["processingRunState"] != "superseded" for m in after["manifests"]):
                raise RuntimeError("Historical evidence did not retain explicit superseded state.")
            statuses = [
                client.get(base + "/pages/501/render").status_code,
                client.get(base.replace(str(source.document_id), str(uuid4()))).status_code,
                client.get(
                    base.replace(str(run.binding.parse_generation_id), str(uuid4()))
                ).status_code,
            ]
            if statuses != [404, 404, 404]:
                raise RuntimeError("Invalid retained source identities did not fail closed.")
            _revoke_token(token_id)
            if client.get(base).status_code != 401:
                raise RuntimeError("Revoked evidence credential remained usable.")
            write_private(
                output_dir / "retained-evidence-api.json", {"before": before, "after": after}
            )
            return {
                "transport": "authenticated_in_process_asgi",
                "page_count": first.total,
                "historical_page_and_render_replay_equal": True,
                "unauthenticated_status": 401,
                "revoked_credential_http_status": 401,
                "invalid_identity_statuses": statuses,
                "later_run_invocations": 0,
                "render_sha256": [r["sha256"] for r in before["renders"]],
            }
    finally:
        _revoke_token(token_id)


def _capture_pages(client: TestClient, base: str) -> dict[str, Any]:
    manifests, pages, renders = [], [], []
    total = 1
    for offset in range(500):
        if offset >= total:
            break
        response = client.get(base, params={"offset": offset, "limit": 1})
        response.raise_for_status()
        manifest = GenerationEvidenceManifest.model_validate(response.json())
        total = manifest.total
        if len(manifest.pages) != 1 or manifest.pages[0].page_number != offset + 1:
            raise RuntimeError("Retained evidence pagination lost its exact page denominator.")
        summary = manifest.pages[0]
        if summary.render is None or summary.render_registration != "registered":
            raise RuntimeError("A source page is missing its retained image.")
        response = client.get(base + f"/pages/{offset + 1}")
        response.raise_for_status()
        page = GenerationEvidencePage.model_validate(response.json())
        if page.page.id != summary.page_id or page.render != summary.render:
            raise RuntimeError("Page detail changed the retained manifest identity.")
        response = client.get(summary.render.image_url)
        response.raise_for_status()
        digest = hashlib.sha256(response.content).hexdigest()
        if (
            digest != summary.render.sha256
            or len(response.content) != summary.render.byte_size
            or response.headers.get("cache-control") != "private, no-store"
            or response.headers.get("content-type") != "image/png"
        ):
            raise RuntimeError("Protected page bytes differ from their retained source identity.")
        manifests.append(manifest.model_dump(mode="json", by_alias=True))
        pages.append(page.model_dump(mode="json", by_alias=True))
        renders.append(
            {"page_number": offset + 1, "sha256": digest, "byte_size": len(response.content)}
        )
    return {"manifests": manifests, "pages": pages, "renders": renders}


def _cancel_successor(source: ProbeSource, manifest: GenerationEvidenceManifest) -> None:
    household_id = source.principal.household_id
    if household_id is None:
        raise RuntimeError("Probe source has no authenticated household.")
    service = DocumentProcessingService()
    successor = service.start_parse(
        document_id=source.document_id,
        principal=source.principal,
        original_asset_id=source.asset_id,
        original_sha256=source.stored.sha256,
        request_key=uuid4(),
        configuration=manifest.parser_configuration,
        queue_name=f"unclaimed-history-probe-{uuid4()}",
    )
    # Never claimed or sent to a model; only the history transition is exercised.
    service.cancel(
        successor.binding,
        DocumentAccessContext(
            user_id=source.principal.user_id,
            household_id=household_id,
            household_role=source.principal.household_role,
        ),
    )


def _reader_token(source: ProbeSource) -> tuple[str, UUID]:
    token = secrets.token_urlsafe(32)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO api_tokens (user_id,household_id,label,token_hash,scopes) "
            "VALUES (%s,%s,'Isolated retained evidence probe',%s,ARRAY['documents:read']) "
            "RETURNING id",
            (source.principal.user_id, source.principal.household_id, hash_secret(token)),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Probe evidence reader token was not created.")
        return token, row["id"]


def _revoke_token(token_id: UUID) -> None:
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE api_tokens SET revoked_at=clock_timestamp() WHERE id=%s", (token_id,))
