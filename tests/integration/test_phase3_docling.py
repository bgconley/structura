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
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.documents.parse_models import (
    CanonicalParseResult,
    ParsedChunk,
    ParsedElement,
    ParsedPage,
    ParsedTable,
)
from workers.docling import worker as docling_worker


class FixtureDoclingConverter:
    def __init__(self, marker: str = "initial") -> None:
        self.marker = marker

    def convert(
        self,
        source_path: Path,
        *,
        filename: str,
        mime_type: str,
    ) -> CanonicalParseResult:
        assert source_path.exists()
        pages = [
            ParsedPage(
                page_number=1,
                text=f"Phase 3 fixture page one {self.marker}",
                width=612,
                height=792,
                has_text_layer=True,
                metadata={"fixture": self.marker},
            ),
            ParsedPage(
                page_number=2,
                text=f"Phase 3 fixture page two {self.marker}",
                width=612,
                height=792,
                has_text_layer=True,
                metadata={"fixture": self.marker},
            ),
        ]
        payload = {
            "fixture": self.marker,
            "filename": filename,
            "mime_type": mime_type,
            "pages": {
                "1": {"text": pages[0].text, "size": {"width": 612, "height": 792}},
                "2": {"text": pages[1].text, "size": {"width": 612, "height": 792}},
            },
        }
        return CanonicalParseResult(
            docling_json=payload,
            json_bytes=json.dumps(payload, sort_keys=True).encode("utf-8"),
            markdown_bytes=f"# Fixture {self.marker}\n\n{pages[0].text}".encode(),
            html_bytes=f"<main><p>{pages[0].text}</p></main>".encode(),
            pages=pages,
            elements=[
                ParsedElement(
                    page_number=1,
                    element_type="paragraph",
                    ordinal=1,
                    text=pages[0].text,
                    bbox={"l": 10, "t": 20, "r": 500, "b": 80},
                    source_ref="#/texts/0",
                )
            ],
            tables=[
                ParsedTable(
                    page_number=2,
                    table_index=1,
                    row_count=2,
                    column_count=2,
                    table_json={"cells": [["a", "b"], ["c", "d"]]},
                    table_markdown="| a | b |\n| c | d |",
                )
            ],
            chunks=[
                ParsedChunk(
                    chunk_index=1,
                    text=pages[0].text,
                    page_start=1,
                    page_end=1,
                    token_count=6,
                ),
                ParsedChunk(
                    chunk_index=2,
                    text=pages[1].text,
                    page_start=2,
                    page_end=2,
                    token_count=6,
                ),
            ],
            converter_name="docling-fixture",
            converter_version=self.marker,
            metadata={"fixture": True},
        )


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 3 Docling tests.",
)
def test_phase3_docling_worker_persists_parse_assets_and_debug_view(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client = _phase3_client(monkeypatch, tmp_path, "phase3-docling")
    document_id = _upload_fixture_document(client, "Phase 3 Docling Fixture")

    assert docling_worker.process_next_docling_job(
        worker_name="phase3-docling-test",
        document_id=document_id,
        converter=FixtureDoclingConverter(),
    )

    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert len(payload["pages"]) == 2
    assert all(page["imageUrl"].startswith("/api/v1/assets/") for page in payload["pages"])
    assert {asset["assetRole"] for asset in payload["assets"]} >= {
        "original",
        "docling_json",
        "docling_md",
        "docling_html",
        "page_image",
        "thumbnail",
    }

    debug = client.get(f"/api/v1/documents/{document_id}/parse-debug")
    assert debug.status_code == 200
    debug_payload = debug.json()
    assert debug_payload["document"]["pageCount"] == 2
    assert debug_payload["chunks"][0]["textPreview"].startswith("Phase 3 fixture page one")
    assert not _contains_storage_uri(debug_payload)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status::text AS status, result_json
                FROM pipeline_jobs
                WHERE document_id = %s
                  AND job_type = 'docling_convert'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            )
            job = cur.fetchone()
    assert job["status"] == "succeeded"
    assert job["result_json"]["page_count"] == 2


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 3 Docling tests.",
)
def test_phase3_docling_rerun_supersedes_current_assets_without_duplicate_parse_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client = _phase3_client(monkeypatch, tmp_path, "phase3-rerun")
    document_id = _upload_fixture_document(client, "Phase 3 Rerun Fixture")
    assert docling_worker.process_next_docling_job(
        worker_name="phase3-rerun-test",
        document_id=document_id,
        converter=FixtureDoclingConverter("v1"),
    )
    _enqueue_docling_job(document_id)
    assert docling_worker.process_next_docling_job(
        worker_name="phase3-rerun-test",
        document_id=document_id,
        converter=FixtureDoclingConverter("v2"),
    )

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT asset_role::text AS asset_role, page_number, count(*) AS current_count
                FROM document_assets
                WHERE document_id = %s
                  AND is_current
                  AND asset_role IN (
                    'docling_json',
                    'docling_md',
                    'docling_html',
                    'page_image',
                    'thumbnail'
                  )
                GROUP BY asset_role, page_number
                HAVING count(*) <> 1
                """,
                (document_id,),
            )
            duplicate_current_assets = cur.fetchall()
            cur.execute(
                "SELECT count(*) AS total FROM document_pages WHERE document_id = %s",
                (document_id,),
            )
            page_count = cur.fetchone()["total"]
            cur.execute(
                "SELECT count(*) AS total FROM document_chunks WHERE document_id = %s",
                (document_id,),
            )
            chunk_count = cur.fetchone()["total"]
            cur.execute(
                """
                SELECT count(*) AS total
                FROM document_assets
                WHERE document_id = %s
                  AND asset_role = 'docling_json'
                  AND is_current = false
                """,
                (document_id,),
            )
            historical_json_count = cur.fetchone()["total"]

    assert duplicate_current_assets == []
    assert page_count == 2
    assert chunk_count == 2
    assert historical_json_count >= 1


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 3 Docling tests.",
)
def test_phase3_parse_debug_is_admin_scoped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    owner_client = _phase3_client(monkeypatch, tmp_path, "phase3-debug-owner")
    document_id = _upload_fixture_document(owner_client, "Phase 3 Debug Auth Fixture")

    other_client = _phase3_client(monkeypatch, tmp_path, "phase3-debug-other")
    hidden = other_client.get(f"/api/v1/documents/{document_id}/parse-debug")
    assert hidden.status_code == 404

    anonymous = TestClient(create_app())
    denied = anonymous.get(f"/api/v1/documents/{document_id}/parse-debug")
    assert denied.status_code == 401


def _phase3_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    label: str,
) -> TestClient:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / f"runtime-{label}"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"{label}-{unique}@example.com"
    password = "minimum8"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name=f"{label} Admin",
        household_name=f"{label} {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    return client


def _upload_fixture_document(client: TestClient, title: str) -> uuid.UUID:
    accepted = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
        data={"source": "web_upload", "suppliedTitle": title},
        files={"file": ("phase3.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert accepted.status_code == 202
    listed = client.get("/api/v1/documents", params={"q": title})
    assert listed.status_code == 200
    return uuid.UUID(listed.json()["items"][0]["id"])


def _enqueue_docling_job(document_id: uuid.UUID) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT household_id, batch_id
                FROM documents
                WHERE id = %s
                """,
                (document_id,),
            )
            document = cur.fetchone()
            cur.execute(
                """
                INSERT INTO pipeline_jobs
                  (household_id, job_type, document_id, batch_id, payload_json, queue_name)
                VALUES (%s, 'docling_convert', %s, %s, %s::jsonb, 'docling')
                """,
                (
                    document["household_id"],
                    document_id,
                    document["batch_id"],
                    json.dumps({"document_id": str(document_id), "stage": "phase3.rerun"}),
                ),
            )
        conn.commit()


def _contains_storage_uri(value: object) -> bool:
    if isinstance(value, dict):
        return any(_contains_storage_uri(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_storage_uri(child) for child in value)
    return isinstance(value, str) and "filesystem://" in value
