from __future__ import annotations

import json
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("psycopg")

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.auth.service import hash_password
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.relationships.service import RelationshipService
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
def test_phase7_related_counts_do_not_reveal_hidden_counterparts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    owner, owner_csrf, household_id, _owner_id = _phase7_client(monkeypatch, tmp_path, "acl-count")
    unique = uuid.uuid4().hex[:8]
    viewer = _same_household_client(
        household_id=household_id,
        email=f"phase7-acl-viewer-{unique}@example.com",
        role="viewer",
    )
    visible_id = _upload_document(owner, owner_csrf, f"Visible Relationship Anchor {unique}")
    hidden_id = _upload_document(owner, owner_csrf, f"Hidden Relationship Counterpart {unique}")
    visible_folder_id = _create_folder(
        owner,
        owner_csrf,
        name=f"Household Links {unique}",
        acl_mode="household",
    )
    private_folder_id = _create_folder(
        owner,
        owner_csrf,
        name=f"Private Links {unique}",
        acl_mode="private",
    )
    _file_document(owner, owner_csrf, visible_id, visible_folder_id)
    _file_document(owner, owner_csrf, hidden_id, private_folder_id)

    created = owner.post(
        "/api/v1/relationships",
        headers={"X-CSRF-Token": owner_csrf},
        json={
            "fromDocumentId": visible_id,
            "toDocumentId": hidden_id,
            "relationshipType": "related_to",
            "confidence": 0.93,
            "comment": "Hidden counterpart should not leak through counts.",
            "evidence": [
                {
                    "pageNumber": 1,
                    "sourceEngine": "human",
                    "sourceText": "The hidden document is linked to the visible one.",
                }
            ],
        },
    )
    assert created.status_code == 201

    viewer_list = viewer.get(
        "/api/v1/documents",
        params={"q": f"Visible Relationship Anchor {unique}"},
    )
    assert viewer_list.status_code == 200
    assert viewer_list.json()["total"] == 1
    assert viewer_list.json()["items"][0]["relatedCount"] == 0

    viewer_detail = viewer.get(f"/api/v1/documents/{visible_id}")
    assert viewer_detail.status_code == 200
    assert viewer_detail.json()["relatedCount"] == 0
    assert viewer_detail.json()["relationships"] == []


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 7 relationship tests.",
)
def test_phase7_contact_timeline_excludes_unrelated_relationship_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, csrf, _household_id, _user_id = _phase7_client(
        monkeypatch,
        tmp_path,
        "contact-timeline",
    )
    unique = uuid.uuid4().hex[:8]
    contact_doc_id = _upload_document(client, csrf, f"Timeline Contact Anchor {unique}")
    unrelated_left_id = _upload_document(client, csrf, f"Timeline Unrelated Left {unique}")
    unrelated_right_id = _upload_document(client, csrf, f"Timeline Unrelated Right {unique}")

    contact = client.post(
        "/api/v1/contacts",
        headers={"X-CSRF-Token": csrf},
        json={"displayName": f"Timeline Contact {unique}", "contactType": "vendor"},
    )
    assert contact.status_code == 201
    contact_id = contact.json()["id"]
    linked = client.post(
        f"/api/v1/documents/{contact_doc_id}/contacts",
        headers={"X-CSRF-Token": csrf},
        json={
            "contactId": contact_id,
            "roleName": "vendor",
            "confidence": 0.97,
            "evidence": {
                "pageNumber": 1,
                "sourceEngine": "human",
                "sourceText": "Contact appears on the document.",
            },
        },
    )
    assert linked.status_code == 201

    relationship = client.post(
        "/api/v1/relationships",
        headers={"X-CSRF-Token": csrf},
        json={
            "fromDocumentId": unrelated_left_id,
            "toDocumentId": unrelated_right_id,
            "relationshipType": "related_to",
            "confidence": 0.91,
            "comment": "Unrelated pair.",
            "evidence": [{"pageNumber": 1, "sourceEngine": "human", "sourceText": "Unrelated."}],
        },
    )
    assert relationship.status_code == 201
    unrelated_relationship_id = relationship.json()["id"]

    timeline = client.get("/api/v1/timeline", params={"contactId": contact_id})
    assert timeline.status_code == 200
    events = timeline.json()["items"]
    assert any(
        item["eventType"] == "document" and item["documentId"] == contact_doc_id for item in events
    )
    assert all(item.get("relationshipId") != unrelated_relationship_id for item in events)


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 7 relationship tests.",
)
def test_phase7_refreshed_deadlines_receive_deterministic_lifecycle_statuses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, csrf, _household_id, _user_id = _phase7_client(monkeypatch, tmp_path, "deadline-status")
    document_id = uuid.UUID(
        _upload_document(client, csrf, f"Deadline Status {uuid.uuid4().hex[:8]}")
    )
    today = date.today()
    _insert_deadline_field(document_id, "invoice.due_date", today - timedelta(days=2))
    _insert_deadline_field(document_id, "warranty.expiration_date", today + timedelta(days=10))
    _insert_deadline_field(document_id, "contract.renewal_date", today + timedelta(days=90))

    assert RelationshipService().refresh_deadlines(document_id) == 3

    listed = client.get("/api/v1/deadlines", params={"documentId": str(document_id)})
    assert listed.status_code == 200
    statuses = {item["deadlineType"]: item["status"] for item in listed.json()["items"]}
    assert statuses["due_date"] == "overdue"
    assert statuses["warranty_expiration"] == "due_soon"
    assert statuses["renewal_date"] == "open"


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


def _same_household_client(*, household_id: uuid.UUID, email: str, role: str) -> TestClient:
    password = "minimum8"
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, display_name)
                VALUES (%s, %s)
                RETURNING id
                """,
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
                VALUES (%s, %s, %s)
                """,
                (household_id, user_id, role),
            )
        conn.commit()
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    return client


def _create_folder(client: TestClient, csrf: str, *, name: str, acl_mode: str) -> str:
    created = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={"folderKind": "manual", "name": name, "aclMode": acl_mode},
    )
    assert created.status_code == 201
    return str(created.json()["id"])


def _file_document(client: TestClient, csrf: str, document_id: str, folder_id: str) -> None:
    filed = client.post(
        f"/api/v1/documents/{document_id}/organization",
        headers={"X-CSRF-Token": csrf},
        json={"folderIds": [folder_id], "primaryFolderId": folder_id},
    )
    assert filed.status_code == 200


def _insert_deadline_field(document_id: uuid.UUID, field_path: str, due_on: date) -> None:
    evidence = [
        {
            "pageNumber": 1,
            "sourceEngine": "system",
            "sourceText": f"{field_path} is {due_on.isoformat()}",
        }
    ]
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO field_candidates
                  (document_id, field_path, source_engine, value_type, date_value,
                   confidence, evidence_json, status)
                VALUES (%s, %s, 'system', 'date', %s, 0.93, %s::jsonb, 'promoted')
                RETURNING id
                """,
                (document_id, field_path, due_on, _json_evidence(evidence)),
            )
            candidate_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO canonical_fields
                  (document_id, selected_candidate_id, field_path, value_type, date_value,
                   source_kind, review_status, evidence_json, accepted_at)
                VALUES (%s, %s, %s, 'date', %s, 'candidate', 'auto_accepted', %s::jsonb, now())
                """,
                (document_id, candidate_id, field_path, due_on, _json_evidence(evidence)),
            )
        conn.commit()


def _json_evidence(evidence: list[dict[str, object]]) -> str:
    return json.dumps(evidence)
