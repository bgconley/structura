from __future__ import annotations

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
from workers.relationships.worker import process_next_relationship_job


def _phase7_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    label: str,
) -> tuple[TestClient, str, uuid.UUID, uuid.UUID]:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / f"runtime-{label}"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase7-{label}-{unique}@example.com"
    password = "minimum8"
    bootstrap = AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name=f"Phase 7 {label} Admin",
        household_name=f"Phase 7 {label} {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    return client, client.cookies["structura_csrf"], bootstrap.household_id, bootstrap.user_id


def _upload_document(client: TestClient, csrf: str, title: str) -> str:
    accepted = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload", "suppliedTitle": title},
        files={"file": (f"{title}.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert accepted.status_code == 202
    listed = client.get("/api/v1/documents", params={"q": title})
    assert listed.status_code == 200
    return str(listed.json()["items"][0]["id"])


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 7 relationship tests.",
)
def test_phase7_manual_relationship_detail_timeline_search_and_decisions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, csrf, _household_id, _user_id = _phase7_client(monkeypatch, tmp_path, "manual")
    unique = uuid.uuid4().hex[:8]
    warranty_id = _upload_document(client, csrf, f"Phase7 Warranty {unique}")
    receipt_id = _upload_document(client, csrf, f"Phase7 Receipt {unique}")

    created = client.post(
        "/api/v1/relationships",
        headers={"X-CSRF-Token": csrf},
        json={
            "fromDocumentId": warranty_id,
            "toDocumentId": receipt_id,
            "relationshipType": "warranty_for",
            "confidence": 0.91,
            "comment": "Manual link from receipt packet.",
            "evidence": [
                {
                    "pageNumber": 1,
                    "sourceEngine": "human",
                    "sourceText": "Receipt packet includes warranty card.",
                }
            ],
        },
    )
    assert created.status_code == 201
    relationship_id = created.json()["id"]
    assert created.json()["status"] == "confirmed"
    assert created.json()["relatedDocumentId"] == receipt_id

    detail = client.get(f"/api/v1/documents/{warranty_id}")
    assert detail.status_code == 200
    assert detail.json()["relationships"][0]["id"] == relationship_id
    assert detail.json()["relationships"][0]["relatedTitle"].startswith("Phase7 Receipt")

    listed = client.get("/api/v1/relationships", params={"documentId": warranty_id})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [relationship_id]

    timeline = client.get("/api/v1/timeline", params={"documentId": warranty_id})
    assert timeline.status_code == 200
    assert any(item["eventType"] == "relationship" for item in timeline.json()["items"])

    search = client.post(
        "/api/v1/search",
        json={
            "query": unique,
            "mode": "lexical",
            "relationshipTypes": ["warranty_for"],
            "hasRelationships": True,
            "includeDebug": True,
        },
    )
    assert search.status_code == 200
    assert search.json()["debug"]["filtersApplied"] >= 2

    rejected = client.post(
        f"/api/v1/relationships/{relationship_id}/reject",
        headers={"X-CSRF-Token": csrf},
        json={"comment": "Wrong receipt."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 7 relationship tests.",
)
def test_phase7_relationship_worker_suggests_duplicates_idempotently(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, csrf, _household_id, _user_id = _phase7_client(monkeypatch, tmp_path, "worker")
    unique = uuid.uuid4().hex[:8]
    first_id = _upload_document(client, csrf, f"Phase7 Duplicate A {unique}")
    second_id = _upload_document(client, csrf, f"Phase7 Duplicate B {unique}")

    assert process_next_relationship_job(
        worker_name="phase7-relationships-test",
        document_id=second_id,
    )
    assert _relationship_count(first_id, second_id, "duplicate_of") == 1

    _enqueue_relate_job(second_id)
    assert process_next_relationship_job(
        worker_name="phase7-relationships-test",
        document_id=second_id,
    )
    assert _relationship_count(first_id, second_id, "duplicate_of") == 1

    suggestions = client.get(
        "/api/v1/relationships",
        params={"documentId": second_id, "status": "suggested"},
    )
    assert suggestions.status_code == 200
    assert suggestions.json()["items"]


def _relationship_count(left_id: str, right_id: str, relationship_type: str) -> int:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM document_relationships
                WHERE relationship_type = %s
                  AND status IN ('suggested', 'confirmed')
                  AND (
                    (from_document_id = %s AND to_document_id = %s)
                    OR (from_document_id = %s AND to_document_id = %s)
                  )
                """,
                (relationship_type, left_id, right_id, right_id, left_id),
            )
            row = cur.fetchone()
    return int(row["total"] if row else 0)


def _enqueue_relate_job(document_id: str) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT household_id FROM documents WHERE id = %s", (document_id,))
            row = cur.fetchone()
            assert row
            cur.execute(
                """
                INSERT INTO pipeline_jobs
                  (household_id, job_type, document_id, payload_json, priority, queue_name)
                VALUES (%s, 'relate', %s, %s::jsonb, 45, 'relationships')
                """,
                (row["household_id"], document_id, '{"stage":"phase7.relate"}'),
            )
        conn.commit()
