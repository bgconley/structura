from __future__ import annotations

import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to an isolated migrated database.",
)


def test_corrections_reject_invalid_values_without_mutation_and_preserve_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "correction-runtime"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    unique = uuid4().hex
    email = f"correction-{unique}@example.com"
    AuthService().bootstrap_admin(
        email=email,
        password="minimum8",
        display_name="Correction Reviewer",
        household_name=f"Correction {unique}",
        must_rotate=False,
    )
    try:
        with TestClient(create_app()) as client:
            login = client.post(
                "/api/v1/auth/session",
                json={"method": "password", "email": email, "password": "minimum8"},
            )
            assert login.status_code == 201
            headers = {"X-CSRF-Token": client.cookies["structura_csrf"]}
            upload = client.post(
                "/api/v1/documents",
                headers=headers,
                data={"source": "web_upload", "suppliedTitle": unique},
                files={"file": ("correction.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
            )
            assert upload.status_code == 202
            documents = client.get("/api/v1/documents", params={"q": unique}).json()["items"]
            document_id = UUID(documents[0]["id"])
            _exercise_corrections(client, headers, document_id)
    finally:
        get_settings.cache_clear()


def _exercise_corrections(client: TestClient, headers: dict[str, str], document_id: UUID) -> None:
    evidence = [{"pageNumber": 1, "sourceEngine": "human", "sourceText": "Reviewed total"}]
    base = {
        "fieldPath": "invoice.total_amount",
        "valueType": "money",
        "sourceKind": "human",
        "currency": "USD",
        "evidence": evidence,
        "reason": "Initial reviewed amount",
    }
    path = f"/api/v1/documents/{document_id}"
    initial = client.post(
        f"{path}/canonical-fields",
        headers=headers,
        json={**base, "value": {"amount": 12.50, "currency": "USD"}},
    )
    assert initial.status_code == 200
    baseline = _snapshot(document_id)
    for value_type, value in [
        ("money", {"amount": "abc", "currency": "USD"}),
        ("money", {"amount": 1, "currency": "EUR"}),
        ("number", 1.23456),
        ("number", 1e14),
        ("integer", 12.5),
        ("boolean", "false"),
        # Changing the declared type must not bypass an existing money field.
        ("string", "not a total"),
    ]:
        for endpoint in ("canonical-fields", "review-actions"):
            payload = (
                {**base, "valueType": value_type, "value": value}
                if endpoint == "canonical-fields"
                else {
                    "documentId": str(document_id),
                    "actionType": "correct_field",
                    "fieldPath": base["fieldPath"],
                    "newValue": value,
                    "evidenceContext": evidence,
                    "metadata": {"valueType": value_type, "currency": "USD"},
                }
            )
            response = client.post(f"{path}/{endpoint}", headers=headers, json=payload)
            assert response.status_code == 422, response.text
            assert _snapshot(document_id) == baseline

    for amount in (0, -12.3456):
        revision = client.get(f"{path}/canonical-fields").json()["items"][0]["updatedAt"]
        response = client.post(
            f"{path}/review-actions",
            headers=headers,
            json={
                "documentId": str(document_id),
                "actionType": "correct_field",
                "fieldPath": base["fieldPath"],
                "newValue": {"amount": amount, "currency": "USD"},
                "expectedUpdatedAt": revision,
                "evidenceContext": evidence,
                "metadata": {"valueType": "money", "currency": "USD"},
                "comment": f"Reviewed amount {amount}",
            },
        )
        assert response.status_code == 200
        fields = client.get(f"{path}/canonical-fields").json()["items"]
        assert fields[0]["value"] == {"amount": amount, "currency": "USD"}
        assert fields[0]["reviewStatus"] == "user_corrected"
        assert fields[0]["evidence"][0]["sourceText"] == "Reviewed total"

    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT numeric_value, currency_code FROM canonical_fields WHERE document_id = %s",
            (document_id,),
        )
        row = cur.fetchone()
        assert row["numeric_value"] == Decimal("-12.3456")
        assert row["currency_code"] == "USD"
        cur.execute(
            """SELECT old_value_json, new_value_json, actor_user_id, reason
               FROM canonical_fact_history WHERE document_id = %s ORDER BY created_at""",
            (document_id,),
        )
        history = cur.fetchall()
        assert len(history) == 3
        assert history[1]["old_value_json"] == {"amount": 12.5, "currency": "USD"}
        assert history[1]["new_value_json"]["value"] == {"amount": 0, "currency": "USD"}
        assert history[2]["old_value_json"] == {"amount": 0, "currency": "USD"}
        assert history[2]["new_value_json"]["value"] == {"amount": -12.3456, "currency": "USD"}
        assert all(row["actor_user_id"] and row["reason"] for row in history)


def _snapshot(document_id: UUID) -> tuple[object, object]:
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT to_jsonb(cf) AS value FROM canonical_fields cf "
            "WHERE document_id = %s ORDER BY id",
            (document_id,),
        )
        fields = cur.fetchall()
        cur.execute(
            """SELECT
                (SELECT count(*) FROM canonical_fact_history WHERE document_id = %(id)s) AS history,
                (SELECT count(*) FROM review_events WHERE document_id = %(id)s) AS events,
                (SELECT count(*) FROM pipeline_jobs WHERE document_id = %(id)s) AS jobs,
                (SELECT count(*) FROM field_candidates WHERE document_id = %(id)s) AS candidates""",
            {"id": document_id},
        )
        return fields, cur.fetchone()
