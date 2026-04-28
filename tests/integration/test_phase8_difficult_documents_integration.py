from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("psycopg")

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.auth.service import hash_password
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.documents.parse_models import CanonicalParseResult, ParsedChunk, ParsedPage
from workers.docling import worker as docling_worker
from workers.embeddings import worker as embeddings_worker
from workers.extraction import worker as extraction_worker


class Phase8DoclingConverter:
    def __init__(
        self,
        text: str,
        *,
        page_metadata: dict[str, object],
        has_text_layer: bool | None,
        ocr_confidence: float | None = None,
        include_chunk: bool = True,
    ) -> None:
        self.text = text
        self.page_metadata = page_metadata
        self.has_text_layer = has_text_layer
        self.ocr_confidence = ocr_confidence
        self.include_chunk = include_chunk

    def convert(
        self,
        source_path: Path,
        *,
        filename: str,
        mime_type: str,
    ) -> CanonicalParseResult:
        assert source_path.exists()
        chunks = (
            [ParsedChunk(chunk_index=1, text=self.text, page_start=1, page_end=1)]
            if self.include_chunk and self.text
            else []
        )
        return CanonicalParseResult(
            docling_json={
                "filename": filename,
                "mime_type": mime_type,
                "text": self.text,
                "phase": "phase8-test",
            },
            json_bytes=json.dumps({"text": self.text}).encode(),
            markdown_bytes=self.text.encode(),
            html_bytes=f"<main><p>{self.text}</p></main>".encode(),
            pages=[
                ParsedPage(
                    page_number=1,
                    text=self.text,
                    width=612,
                    height=792,
                    has_text_layer=self.has_text_layer,
                    ocr_confidence=self.ocr_confidence,
                    metadata=self.page_metadata,
                )
            ],
            elements=[],
            tables=[],
            chunks=chunks,
            converter_name="phase8-difficult-doc-fixture",
            converter_version="v1",
            metadata={"fixture": True},
        )


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 8 difficult-document tests.",
)
def test_phase8_low_text_handwriting_gets_review_task_visual_embedding_and_visual_search(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, csrf, household_id = _phase8_client(monkeypatch, tmp_path, "visual")
    unique = uuid.uuid4().hex[:8]
    title = f"Phase8 handwritten intake {unique}"
    document_id = _upload_fixture_document(client, csrf, title)

    assert docling_worker.process_next_docling_job(
        worker_name="phase8-docling-test",
        document_id=document_id,
        converter=Phase8DoclingConverter(
            "",
            page_metadata={
                "hasHandwriting": True,
                "visualQuality": "degraded",
                "parseWarnings": ["image-only page"],
            },
            has_text_layer=False,
            ocr_confidence=0.38,
            include_chunk=False,
        ),
    )
    _wait_for(lambda: _document_has_phase8_quality(document_id), "phase8 quality metadata")
    assert _review_task_count(document_id, "document_quality") == 1

    assert _process_embedding_queue(
        document_id=document_id,
        queue_name="visual-embeddings",
        worker_name="phase8-visual-embedding-test",
    )
    assert _active_embedding_count(document_id, modality="visual") == 1
    visual_metadata = _active_embedding_metadata(document_id, modality="visual")
    assert visual_metadata["adapter"] == "deterministic_visual_byte_embedding"
    assert visual_metadata["contentSha256"] == visual_metadata["assetSha256"]
    assert visual_metadata["sourceBytesSha256"] == visual_metadata["assetSha256"]

    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    quality = detail.json()["qualitySummary"]
    assert quality["reviewRequired"] is True
    assert "handwriting" in quality["reasons"]
    assert detail.json()["pages"][0]["qualitySignals"]["visualEmbeddingEligible"] is True

    search = client.post(
        "/api/v1/search",
        json={
            "query": f"handwritten degraded intake {unique}",
            "mode": "visual",
            "includeVisual": True,
            "limit": 5,
            "includeDebug": True,
        },
    )
    assert search.status_code == 200
    item = _result_for_document(search.json(), document_id)
    assert item is not None
    assert "visual" in item["sourceModalities"]
    assert "visual" in item["explanation"]

    other_client = _same_household_viewer_client(
        household_id=household_id,
        email=f"phase8-viewer-{unique}@example.com",
    )
    _make_document_private(document_id)
    hidden = other_client.post(
        "/api/v1/search",
        json={"query": unique, "mode": "visual", "includeVisual": True},
    )
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 8 difficult-document tests.",
)
def test_phase8_handwriting_invoice_uses_qwen_route_and_stays_review_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, csrf, _household_id = _phase8_client(monkeypatch, tmp_path, "qwen")
    unique = uuid.uuid4().hex[:8]
    document_id = _upload_fixture_document(client, csrf, f"Phase8 handwritten invoice {unique}")
    text = (
        f"Invoice Number INV-{unique}\n"
        "Seller: Ink Clinic\n"
        "Issue date: 2026-04-20\n"
        "Due date: 2026-05-04\n"
        "Total: $88.00\n"
        "Balance due: $88.00\n"
    )

    assert docling_worker.process_next_docling_job(
        worker_name="phase8-qwen-docling-test",
        document_id=document_id,
        converter=Phase8DoclingConverter(
            text,
            page_metadata={"hasHandwriting": True, "visualQuality": "mixed"},
            has_text_layer=True,
            ocr_confidence=0.66,
        ),
    )
    _drain_extraction_jobs(document_id, worker_name="phase8-qwen-extraction-test")

    candidates = client.get(
        f"/api/v1/documents/{document_id}/field-candidates",
        params={"fieldPath": "invoice.total_amount"},
    )
    assert candidates.status_code == 200
    assert candidates.json()["items"]
    total_candidate = candidates.json()["items"][0]
    assert total_candidate["sourceEngine"] == "docling"
    assert total_candidate["status"] == "needs_review"

    canonical = client.get(f"/api/v1/documents/{document_id}/canonical-fields")
    assert canonical.status_code == 200
    assert all(item["fieldPath"] != "invoice.total_amount" for item in canonical.json()["items"])
    assert _review_task_count(document_id, "field_review") >= 1


def _phase8_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    label: str,
) -> tuple[TestClient, str, uuid.UUID]:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / f"runtime-{label}"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_EMBEDDING_VISUAL_ENABLED", "true")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase8-{label}-{unique}@example.com"
    password = "minimum8"
    bootstrap = AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name=f"Phase 8 {label} Admin",
        household_name=f"Phase 8 {label} {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    return client, client.cookies["structura_csrf"], bootstrap.household_id


def _upload_fixture_document(client: TestClient, csrf: str, title: str) -> uuid.UUID:
    accepted = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload", "suppliedTitle": title},
        files={"file": ("phase8.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert accepted.status_code == 202
    listed = client.get("/api/v1/documents", params={"q": title})
    assert listed.status_code == 200
    return uuid.UUID(listed.json()["items"][0]["id"])


def _process_embedding_queue(*, document_id: uuid.UUID, queue_name: str, worker_name: str) -> bool:
    if _active_embedding_count(document_id, modality="visual") > 0:
        return True
    for _ in range(6):
        if embeddings_worker.process_next_embedding_job(
            worker_name=worker_name,
            queue_name=queue_name,
            document_id=document_id,
        ):
            return True
        if _active_embedding_count(document_id, modality="visual") > 0:
            return True
        time.sleep(0.2)
    return False


def _drain_extraction_jobs(document_id: uuid.UUID, *, worker_name: str) -> None:
    for _ in range(6):
        extraction_worker.process_next_extraction_job(
            worker_name=worker_name,
            document_id=document_id,
        )
        if _review_task_count(document_id, "field_review") > 0:
            return
        time.sleep(0.2)
    pytest.fail("Timed out waiting for Phase 8 extraction review tasks.")


def _wait_for(predicate, label: str) -> None:
    for _ in range(20):
        if predicate():
            return
        time.sleep(0.2)
    pytest.fail(f"Timed out waiting for {label}.")


def _document_has_phase8_quality(document_id: uuid.UUID) -> bool:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT metadata_json ? 'phase8' AS has_phase8 FROM documents WHERE id = %s",
                (document_id,),
            )
            row = cur.fetchone()
    return bool(row and row["has_phase8"])


def _review_task_count(document_id: uuid.UUID, task_type: str) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS total
                FROM review_tasks
                WHERE document_id = %s
                  AND task_type = %s
                  AND status IN ('open', 'in_progress')
                """,
                (document_id, task_type),
            )
            row = cur.fetchone()
    return int(row["total"] if row else 0)


def _active_embedding_count(document_id: uuid.UUID, *, modality: str) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS total
                FROM embeddings
                WHERE document_id = %s
                  AND modality = %s
                  AND is_active
                """,
                (document_id, modality),
            )
            row = cur.fetchone()
    return int(row["total"] if row else 0)


def _active_embedding_metadata(document_id: uuid.UUID, *, modality: str) -> dict[str, object]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT metadata_json
                FROM embeddings
                WHERE document_id = %s
                  AND modality = %s
                  AND is_active
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id, modality),
            )
            row = cur.fetchone()
    assert row
    return dict(row["metadata_json"] or {})


def _result_for_document(
    payload: dict[str, object],
    document_id: uuid.UUID,
) -> dict[str, object] | None:
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    return next(
        (
            item
            for item in items
            if isinstance(item, dict) and item.get("documentId") == str(document_id)
        ),
        None,
    )


def _same_household_viewer_client(*, household_id: uuid.UUID, email: str) -> TestClient:
    password = "minimum8"
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, display_name) VALUES (%s, %s) RETURNING id",
                (email, email),
            )
            user_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO user_password_credentials
                  (user_id, password_hash, hash_algorithm, params_json, must_rotate, disabled_at)
                VALUES (%s, %s, 'argon2id', '{}'::jsonb, false, NULL)
                """,
                (user_id, hash_password(password)),
            )
            cur.execute(
                """
                INSERT INTO household_memberships (household_id, user_id, role)
                VALUES (%s, %s, 'viewer')
                """,
                (household_id, user_id),
            )
        conn.commit()
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    return client


def _make_document_private(document_id: uuid.UUID) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE documents
                SET acl_mode = 'private',
                    sensitivity = 'normal',
                    primary_folder_id = NULL
                WHERE id = %s
                """,
                (document_id,),
            )
            cur.execute("SELECT refresh_document_chunk_projection(%s)", (document_id,))
        conn.commit()
