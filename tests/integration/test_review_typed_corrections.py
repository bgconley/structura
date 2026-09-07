from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Requires the isolated migrated correction database.",
)


@pytest.fixture
def reviewers(monkeypatch, tmp_path):
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "typed-correction-runtime"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    people = [
        AuthService().bootstrap_admin(
            email=f"typed-{uuid4()}@example.com",
            password="minimum8",
            household_name=f"Typed review {uuid4()}",
            must_rotate=False,
        )
        for _ in range(2)
    ]
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM household_memberships WHERE user_id=%s", (people[1].user_id,))
        cur.execute(
            "INSERT INTO household_memberships (household_id,user_id,role) VALUES (%s,%s,'member')",
            (people[0].household_id, people[1].user_id),
        )
        cur.execute(
            "INSERT INTO documents (title,ingestion_source,household_id,owner_user_id) "
            "VALUES ('Typed corrections','web_upload',%s,%s) RETURNING id",
            (people[0].household_id, people[1].user_id),
        )
        document_id = cur.fetchone()["id"]
    try:
        with TestClient(create_app()) as first, TestClient(create_app()) as second:
            for client, person in zip((first, second), people, strict=True):
                login = client.post(
                    "/api/v1/auth/session",
                    json={"method": "password", "email": person.email, "password": "minimum8"},
                )
                assert login.status_code == 201, login.text
                client.headers["X-CSRF-Token"] = client.cookies["structura_csrf"]
            yield first, second, document_id, people
    finally:
        get_settings.cache_clear()


def write(
    client,
    document_id,
    field,
    kind,
    value,
    *,
    endpoint="canonical-fields",
    revision=None,
    decision_revision=None,
    supplied=True,
):
    evidence = [{"pageNumber": 1, "sourceEngine": "human", "sourceText": "Original typed evidence"}]
    payload = {
        "fieldPath": field,
        "valueType": kind,
        "value": value,
        "sourceKind": "human",
        "evidence": evidence,
        "reason": "Checked against original",
    }
    if endpoint == "review-actions":
        payload = {
            "documentId": str(document_id),
            "fieldPath": field,
            "actionType": "correct_field",
            "newValue": value,
            "metadata": {"valueType": kind},
            "evidenceContext": evidence,
            "comment": "Checked against original",
        }
    if supplied:
        payload["expectedUpdatedAt"] = revision
        payload["expectedDecisionRevision"] = decision_revision
        payload["expectedPathGuardRevision"] = None
    return client.post(f"/api/v1/documents/{document_id}/{endpoint}", json=payload)


def fields(client, document_id):
    response = client.get(f"/api/v1/documents/{document_id}/canonical-fields")
    assert response.status_code == 200
    return {field["fieldPath"]: field for field in response.json()["items"]}


def snapshot(document_id: UUID):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT to_jsonb(cf) AS row FROM canonical_fields cf WHERE document_id=%s ORDER BY id",
            (document_id,),
        )
        canonical = cur.fetchall()
        cur.execute(
            "SELECT "
            "(SELECT count(*) FROM canonical_fact_history WHERE document_id=%(doc)s) history, "
            "(SELECT count(*) FROM review_events WHERE document_id=%(doc)s) events, "
            "(SELECT count(*) FROM pipeline_jobs WHERE document_id=%(doc)s) jobs",
            {"doc": document_id},
        )
        return canonical, cur.fetchone()


@pytest.mark.parametrize("endpoint", ["canonical-fields", "review-actions"])
def test_typed_values_persist_in_native_columns_and_history(reviewers, endpoint):
    first, _, document_id, people = reviewers
    values = [
        ("document.issued_on", "date", "2024-02-29", "2025-03-01"),
        (
            "document.received_at",
            "datetime",
            "2026-09-07T14:30:00.123456-04:00",
            "2026-09-08T09:10:11.654321Z",
        ),
        (
            "document.details",
            "json",
            {"paid": False, "items": [0, None]},
            ["revised", {"paid": True}],
        ),
        ("document.optional_details", "json", {"note": "remove"}, None),
    ]
    for field, kind, initial, updated in values:
        response = write(first, document_id, field, kind, initial, endpoint=endpoint)
        assert response.status_code == 200, response.text
        loaded = fields(first, document_id)[field]
        response = write(
            first,
            document_id,
            field,
            kind,
            updated,
            endpoint=endpoint,
            revision=loaded["updatedAt"],
            decision_revision=loaded["decision"]["revision"],
        )
        assert response.status_code == 200, response.text
        assert fields(first, document_id)[field]["updatedAt"] != loaded["updatedAt"]
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM canonical_fields WHERE document_id=%s", (document_id,))
        stored = {row["field_path"]: row for row in cur.fetchall()}
        assert stored["document.issued_on"]["date_value"] == date(2025, 3, 1)
        assert stored["document.received_at"]["timestamp_value"] == datetime(
            2026, 9, 8, 9, 10, 11, 654321, tzinfo=UTC
        )
        assert stored["document.received_at"]["text_value"] is None
        assert stored["document.details"]["json_value"] == ["revised", {"paid": True}]
        assert stored["document.optional_details"]["json_value"] is None
        cur.execute(
            "SELECT * FROM canonical_fact_history WHERE document_id=%s ORDER BY created_at",
            (document_id,),
        )
        history = cur.fetchall()
        assert len(history) == 8
        assert all(row["actor_user_id"] == people[0].user_id and row["reason"] for row in history)
        date_history = [row for row in history if row["field_path"] == "document.issued_on"]
        assert date_history[1]["old_value_json"] == "2024-02-29"
        assert date_history[1]["new_value_json"]["value"] == "2025-03-01"
        json_history = [row for row in history if row["field_path"] == "document.details"]
        assert json_history[1]["old_value_json"] == {"paid": False, "items": [0, None]}
        assert json_history[1]["new_value_json"]["value"] == ["revised", {"paid": True}]


@pytest.mark.parametrize("endpoint", ["canonical-fields", "review-actions"])
def test_invalid_typed_values_leave_no_canonical_audit_or_job_effect(reviewers, endpoint):
    first, _, document_id, _ = reviewers
    baseline = snapshot(document_id)
    for kind, value in [
        ("date", "2026-02-30"),
        ("date", "07/09/2026"),
        ("datetime", "2026-09-07T14:30:00"),
        ("datetime", "2026-09-07T14:30:00+02:60"),
        ("datetime", "2026-09-07T14:30:00.1234567Z"),
    ]:
        response = write(first, document_id, "document.date", kind, value, endpoint=endpoint)
        assert response.status_code == 422, response.text
        assert snapshot(document_id) == baseline


def test_two_reviewers_cannot_silently_replace_a_newer_decision(reviewers):
    first, second, document_id, people = reviewers
    field = "document.issued_on"
    assert write(first, document_id, field, "date", "2024-01-01").status_code == 200
    # Both editors load the exact persisted revision, including its microseconds.
    # The production update trigger owns this timestamp; do not override it in a fixture.
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT updated_at FROM canonical_fields WHERE document_id=%s AND field_path=%s",
            (document_id, field),
        )
        persisted_revision = cur.fetchone()["updated_at"]
    loaded = fields(first, document_id)[field]
    revision = loaded["updatedAt"]
    decision_revision = loaded["decision"]["revision"]
    assert datetime.fromisoformat(revision.replace("Z", "+00:00")) == persisted_revision
    assert fields(second, document_id)[field]["updatedAt"] == revision
    accepted = write(
        second,
        document_id,
        field,
        "date",
        "2025-02-01",
        endpoint="review-actions",
        revision=revision,
        decision_revision=decision_revision,
    )
    assert accepted.status_code == 200, accepted.text
    unchanged = snapshot(document_id)
    for endpoint in ("canonical-fields", "review-actions"):
        for supplied, expected in ((True, revision), (True, None), (False, None)):
            conflict = write(
                first,
                document_id,
                field,
                "date",
                "2026-03-01",
                endpoint=endpoint,
                revision=expected,
                decision_revision=decision_revision,
                supplied=supplied,
            )
            assert conflict.status_code == 409, conflict.text
            assert snapshot(document_id) == unchanged
    assert fields(first, document_id)[field]["value"] == "2025-02-01"
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT actor_user_id FROM canonical_fact_history "
            "WHERE document_id=%s ORDER BY created_at",
            (document_id,),
        )
        assert [row["actor_user_id"] for row in cur.fetchall()] == [
            person.user_id for person in people
        ]


def test_simultaneous_corrections_have_one_auditable_winner(reviewers):
    first, second, document_id, _ = reviewers
    field = "document.issued_on"
    assert write(first, document_id, field, "date", "2024-01-01").status_code == 200
    loaded = fields(first, document_id)[field]
    revision = loaded["updatedAt"]
    decision_revision = loaded["decision"]["revision"]
    barrier = Barrier(2)

    def submit(client, value):
        barrier.wait(timeout=5)
        return write(
            client,
            document_id,
            field,
            "date",
            value,
            revision=revision,
            decision_revision=decision_revision,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [
            executor.submit(submit, first, "2025-01-01"),
            executor.submit(submit, second, "2026-01-01"),
        ]
        assert sorted(attempt.result(timeout=15) for attempt in attempts) == [200, 409]
    assert fields(first, document_id)[field]["value"] in {"2025-01-01", "2026-01-01"}
    _, counts = snapshot(document_id)
    assert counts["history"] == counts["events"] == 2


def test_api_tombstone_envelope_and_independent_revision_conflict(reviewers):
    client, _, document_id, _ = reviewers
    path = f"/api/v1/documents/{document_id}"
    field_path = "document.rejected_before_acceptance"
    rejected = client.post(
        f"{path}/review-actions",
        json={
            "documentId": str(document_id),
            "actionType": "reject_field",
            "fieldPath": field_path,
            "expectedUpdatedAt": None,
            "expectedDecisionRevision": None,
            "expectedPathGuardRevision": None,
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["canonical"] is None
    current = client.get(f"{path}/canonical-fields").json()
    assert current["authorityVersion"] == "human_authority.v1"
    assert current["items"] == [] and current["decisions"] == [rejected.json()["decision"]]
    assert current["projection"] == rejected.json()["projection"]
    before = snapshot(document_id)
    conflict = write(client, document_id, field_path, "string", "Explicit replacement")
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == (
        "This field changed since it was loaded. Reload it before saving your decision."
    )
    assert snapshot(document_id) == before
    accepted = write(
        client,
        document_id,
        field_path,
        "string",
        "Explicit replacement",
        decision_revision=current["decisions"][0]["revision"],
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["decision"]["revision"] != current["decisions"][0]["revision"]
    assert accepted.json()["decision"]["canonicalFieldId"] == accepted.json()["id"]
