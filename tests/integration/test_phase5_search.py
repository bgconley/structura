from __future__ import annotations

import json
import os
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


class SearchDoclingConverter:
    def __init__(self, text: str) -> None:
        self.text = text

    def convert(
        self,
        source_path: Path,
        *,
        filename: str,
        mime_type: str,
    ) -> CanonicalParseResult:
        assert source_path.exists()
        return CanonicalParseResult(
            docling_json={"filename": filename, "mime_type": mime_type, "text": self.text},
            json_bytes=json.dumps({"text": self.text}).encode(),
            markdown_bytes=self.text.encode(),
            html_bytes=f"<main><p>{self.text}</p></main>".encode(),
            pages=[
                ParsedPage(
                    page_number=1,
                    text=self.text,
                    width=612,
                    height=792,
                    has_text_layer=True,
                )
            ],
            elements=[],
            tables=[],
            chunks=[ParsedChunk(chunk_index=1, text=self.text, page_start=1, page_end=1)],
            converter_name="phase5-search-fixture",
            converter_version="v1",
            metadata={"fixture": True},
        )


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 5 search tests.",
)
def test_phase5_search_lexical_semantic_hybrid_filters_facets_and_acl(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, csrf, household_id = _phase5_client(monkeypatch, tmp_path, "search")
    unique = uuid.uuid4().hex[:8]
    document_id = _upload_fixture_document(client, csrf, f"Phase5 EOB {unique}")
    text = (
        f"Anthem medical EOB claim ABC123 {unique}. "
        "Patient responsibility amount due is 62.00 after insurance paid part."
    )

    assert docling_worker.process_next_docling_job(
        worker_name="phase5-docling-test",
        document_id=document_id,
        converter=SearchDoclingConverter(text),
    )
    _mark_search_fixture_document(
        document_id=document_id,
        family="medical_eob",
        counterparty="Anthem",
        document_date="2026-04-03",
    )
    assert embeddings_worker.process_next_embedding_job(
        worker_name="phase5-embedding-test",
        document_id=document_id,
    )

    lexical = client.post(
        "/api/v1/search",
        json={
            "query": f"ABC123 {unique}",
            "mode": "lexical",
            "families": ["medical_eob"],
            "includeDebug": True,
        },
    )
    assert lexical.status_code == 200
    lexical_payload = lexical.json()
    lexical_item = _result_for_document(lexical_payload, document_id)
    assert lexical_item is not None
    assert "ABC123" in lexical_item["snippet"]
    assert "<b>" not in lexical_item["snippet"]
    assert lexical_payload["facets"]["families"]["medical_eob"] >= 1
    assert lexical_payload["debug"]["mode"] == "lexical"

    semantic = client.post(
        "/api/v1/search",
        json={
            "query": f"documents where I may still owe money for claim {unique}",
            "mode": "semantic",
            "limit": 5,
        },
    )
    assert semantic.status_code == 200
    semantic_item = _result_for_document(semantic.json(), document_id)
    assert semantic_item is not None
    assert semantic_item["explanation"]

    hybrid = client.post(
        "/api/v1/search",
        json={
            "query": f"claim ABC123 money owed {unique}",
            "mode": "hybrid",
            "families": ["medical_eob"],
            "dateFrom": "2026-01-01",
            "dateTo": "2026-12-31",
            "amountMin": 1,
            "amountMax": 100,
            "limit": 5,
        },
    )
    assert hybrid.status_code == 200
    hybrid_item = _result_for_document(hybrid.json(), document_id)
    assert hybrid_item is not None
    assert hybrid_item["pageNumber"] == 1

    other_client = _same_household_viewer_client(
        household_id=household_id,
        email=f"phase5-viewer-{unique}@example.com",
    )
    _make_document_private(document_id)
    hidden = other_client.post("/api/v1/search", json={"query": unique, "mode": "hybrid"})
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 5 search tests.",
)
def test_phase5_embedding_worker_is_idempotent_and_force_reembed_supersedes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, csrf, _household_id = _phase5_client(monkeypatch, tmp_path, "embedding")
    unique = uuid.uuid4().hex[:8]
    document_id = _upload_fixture_document(client, csrf, f"Phase5 Embed {unique}")
    assert docling_worker.process_next_docling_job(
        worker_name="phase5-embed-docling-test",
        document_id=document_id,
        converter=SearchDoclingConverter(f"Receipt total and grocery pantry supplies {unique}."),
    )

    assert embeddings_worker.process_next_embedding_job(
        worker_name="phase5-embedding-test",
        document_id=document_id,
    )
    assert _active_embedding_count(document_id) == 1

    _enqueue_embedding_job(document_id, force_reembed=False)
    assert embeddings_worker.process_next_embedding_job(
        worker_name="phase5-embedding-test",
        document_id=document_id,
    )
    assert _active_embedding_count(document_id) == 1
    assert _all_embedding_count(document_id) == 1

    _enqueue_embedding_job(document_id, force_reembed=True)
    assert embeddings_worker.process_next_embedding_job(
        worker_name="phase5-embedding-test",
        document_id=document_id,
    )
    assert _active_embedding_count(document_id) == 1
    assert _all_embedding_count(document_id) == 2


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 5 search tests.",
)
def test_phase5_smart_folder_saved_query_executes_without_membership(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, csrf, _household_id = _phase5_client(monkeypatch, tmp_path, "smart-folder")
    unique = uuid.uuid4().hex[:8]
    title = f"Phase5 Smart Folder {unique}"
    document_id = _upload_fixture_document(client, csrf, title)
    folder = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={
            "folderKind": "smart",
            "name": f"Needs Review Phase5 {unique}",
            "savedQuery": {"review_status": ["needs_review"]},
        },
    )
    assert folder.status_code == 201
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE documents SET review_status = 'needs_review' WHERE id = %s",
                (document_id,),
            )
        conn.commit()

    listed = client.get("/api/v1/documents", params={"folderId": folder.json()["id"]})

    assert listed.status_code == 200
    assert any(item["id"] == str(document_id) for item in listed.json()["items"])


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 5 search tests.",
)
def test_phase5_saved_searches_are_household_scoped_and_upsert_by_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, csrf, _household_id = _phase5_client(monkeypatch, tmp_path, "saved-search")
    unique = uuid.uuid4().hex[:8]
    created = client.post(
        "/api/v1/saved-searches",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": f"Medical Claims {unique}",
            "queryText": "claim ABC123",
            "filters": {"families": ["medical_eob"]},
        },
    )
    assert created.status_code == 201

    updated = client.post(
        "/api/v1/saved-searches",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": f"Medical Claims {unique}",
            "queryText": "claim ABC123 still owed",
            "filters": {"families": ["medical_eob"], "reviewedOnly": True},
        },
    )
    assert updated.status_code == 201
    assert updated.json()["id"] == created.json()["id"]

    listed = client.get("/api/v1/saved-searches")
    assert listed.status_code == 200
    matches = [
        item for item in listed.json()["items"] if item["name"] == f"Medical Claims {unique}"
    ]
    assert len(matches) == 1
    assert matches[0]["queryText"] == "claim ABC123 still owed"


def _phase5_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    label: str,
) -> tuple[TestClient, str, uuid.UUID]:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / f"runtime-{label}"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase5-{label}-{unique}@example.com"
    password = "minimum8"
    bootstrap = AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name=f"Phase 5 {label} Admin",
        household_name=f"Phase 5 {label} {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    return client, client.cookies["structura_csrf"], bootstrap.household_id


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


def _upload_fixture_document(client: TestClient, csrf: str, title: str) -> uuid.UUID:
    accepted = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload", "suppliedTitle": title},
        files={"file": ("phase5.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert accepted.status_code == 202
    listed = client.get("/api/v1/documents", params={"q": title})
    assert listed.status_code == 200
    return uuid.UUID(listed.json()["items"][0]["id"])


def _mark_search_fixture_document(
    *,
    document_id: uuid.UUID,
    family: str,
    counterparty: str,
    document_date: str,
) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE documents
                SET document_family = %s,
                    counterparty_display = %s,
                    document_date = %s,
                    review_status = 'user_confirmed'
                WHERE id = %s
                """,
                (family, counterparty, document_date, document_id),
            )
            cur.execute(
                """
                INSERT INTO document_amounts
                  (document_id, amount_role, amount, currency_code, metadata_json)
                VALUES (%s, 'total', 62.00, 'USD', '{"phase":"phase5-test"}'::jsonb)
                """,
                (document_id,),
            )
            cur.execute("SELECT refresh_document_chunk_projection(%s)", (document_id,))
        conn.commit()


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


def _enqueue_embedding_job(document_id: uuid.UUID, *, force_reembed: bool) -> None:
    from lib.search.jobs import enqueue_embed_document_job

    with db_connection() as conn:
        with conn.cursor() as cur:
            enqueue_embed_document_job(cur, document_id=document_id, force_reembed=force_reembed)
        conn.commit()


def _active_embedding_count(document_id: uuid.UUID) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS total
                FROM embeddings
                WHERE document_id = %s
                  AND is_active
                  AND modality = 'text'
                """,
                (document_id,),
            )
            return int(cur.fetchone()["total"])


def _all_embedding_count(document_id: uuid.UUID) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS total
                FROM embeddings
                WHERE document_id = %s
                  AND modality = 'text'
                """,
                (document_id,),
            )
            return int(cur.fetchone()["total"])
