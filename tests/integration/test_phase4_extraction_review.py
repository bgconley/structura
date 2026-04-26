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
from lib.documents.parse_models import CanonicalParseResult, ParsedChunk, ParsedElement, ParsedPage
from workers.docling import worker as docling_worker
from workers.extraction import worker as extraction_worker


class TextDoclingConverter:
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
        page = ParsedPage(
            page_number=1,
            text=self.text,
            width=612,
            height=792,
            has_text_layer=True,
        )
        payload = {"filename": filename, "mime_type": mime_type, "text": self.text}
        return CanonicalParseResult(
            docling_json=payload,
            json_bytes=json.dumps(payload).encode(),
            markdown_bytes=self.text.encode(),
            html_bytes=f"<main><p>{self.text}</p></main>".encode(),
            pages=[page],
            elements=[
                ParsedElement(
                    page_number=1,
                    element_type="paragraph",
                    ordinal=1,
                    text=self.text,
                    bbox={"l": 10, "t": 20, "r": 500, "b": 160},
                    source_ref="#/texts/0",
                )
            ],
            tables=[],
            chunks=[ParsedChunk(chunk_index=1, text=self.text, page_start=1, page_end=1)],
            converter_name="phase4-fixture",
            converter_version="v1",
            metadata={"fixture": True},
        )


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 4 extraction tests.",
)
def test_phase4_invoice_extraction_persists_candidates_canonical_and_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client = _phase4_client(monkeypatch, tmp_path, "invoice")
    document_id = _upload_fixture_document(
        client,
        f"Phase 4 Invoice {uuid.uuid4().hex[:8]}",
    )
    text = """
    Seller: Acme Repairs
    Buyer: Structura Household
    Invoice Number: INV-4242
    Issue Date: 2026-04-01
    Due Date: 2026-04-30
    Subtotal: 1000.00
    Tax: 42.15
    Total: 1042.15
    Item: Dishwasher service 1042.15
    """

    assert docling_worker.process_next_docling_job(
        worker_name="phase4-docling-test",
        document_id=document_id,
        converter=TextDoclingConverter(text),
    )
    assert extraction_worker.process_next_extraction_job(
        worker_name="phase4-extraction-test",
        document_id=document_id,
    )
    assert extraction_worker.process_next_extraction_job(
        worker_name="phase4-extraction-test",
        document_id=document_id,
    )

    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["family"] == "invoice"
    assert any(field["fieldPath"] == "invoice.total_amount" for field in payload["fields"])
    assert any(asset["assetRole"] == "raw_model_output" for asset in payload["assets"])
    assert all("filesystem://" not in str(field) for field in payload["fields"])

    candidates = client.get(f"/api/v1/documents/{document_id}/field-candidates")
    assert candidates.status_code == 200
    assert any(item["fieldPath"] == "invoice.total_amount" for item in candidates.json()["items"])

    canonical = client.get(f"/api/v1/documents/{document_id}/canonical-fields")
    assert canonical.status_code == 200
    assert any(item["fieldPath"] == "invoice.total_amount" for item in canonical.json()["items"])

    rerun = client.post(
        f"/api/v1/documents/{document_id}/review-actions",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
        json={
            "schemaName": "review_action",
            "schemaVersion": "v1",
            "documentId": str(document_id),
            "actionType": "rerun_extraction",
            "actorType": "human",
            "metadata": {"targetSchemaName": "invoice"},
            "createdAt": "2026-04-26T00:00:00Z",
        },
    )
    assert rerun.status_code == 200
    rerun_job_id = uuid.UUID(rerun.json()["jobId"])
    assert extraction_worker.process_next_extraction_job(
        worker_name="phase4-rerun-extraction-test",
        document_id=document_id,
    )
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status::text AS status FROM pipeline_jobs WHERE id = %s", (rerun_job_id,)
            )
            assert cur.fetchone()["status"] == "succeeded"
            cur.execute(
                """
                SELECT asset_role::text AS role, count(*) AS total
                FROM document_assets
                WHERE document_id = %s
                  AND is_current
                  AND asset_role IN ('raw_model_output', 'normalized_extraction_json')
                GROUP BY asset_role
                """,
                (document_id,),
            )
            assert {row["role"]: row["total"] for row in cur.fetchall()} == {
                "raw_model_output": 1,
                "normalized_extraction_json": 1,
            }
            cur.execute(
                """
                SELECT count(*) AS total
                FROM document_amounts
                WHERE document_id = %s
                  AND amount_role = 'total'
                  AND metadata_json @> %s::jsonb
                """,
                (document_id, json.dumps({"phase": "phase4", "source": "canonical_fields"})),
            )
            assert cur.fetchone()["total"] == 1


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 4 extraction tests.",
)
def test_phase4_medical_eob_generates_review_task_and_accept_action_is_audited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client = _phase4_client(monkeypatch, tmp_path, "eob")
    document_id = _upload_fixture_document(
        client,
        f"Phase 4 EOB {uuid.uuid4().hex[:8]}",
    )
    text = """
    Explanation of Benefits
    Payer: Blue Plan
    Patient: Jane Example
    Provider: Example Clinic
    Claim Number: CLM-777
    Service: MRI facility
    Total Billed: 500.00
    Total Allowed: 300.00
    Plan Paid: 200.00
    Patient Responsibility: 100.00
    """

    assert docling_worker.process_next_docling_job(
        worker_name="phase4-eob-docling-test",
        document_id=document_id,
        converter=TextDoclingConverter(text),
    )
    assert extraction_worker.process_next_extraction_job(
        worker_name="phase4-eob-extraction-test",
        document_id=document_id,
    )
    assert extraction_worker.process_next_extraction_job(
        worker_name="phase4-eob-extraction-test",
        document_id=document_id,
    )

    tasks = client.get("/api/v1/review-tasks", params={"status": "open"})
    assert tasks.status_code == 200
    assert any(task["documentId"] == str(document_id) for task in tasks.json()["items"])

    candidates = client.get(
        f"/api/v1/documents/{document_id}/field-candidates",
        params={"fieldPath": "medical_eob.total_patient_responsibility"},
    )
    assert candidates.status_code == 200
    candidate_id = candidates.json()["items"][0]["id"]
    accepted = client.post(
        f"/api/v1/documents/{document_id}/review-actions",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
        json={
            "schemaName": "review_action",
            "schemaVersion": "v1",
            "documentId": str(document_id),
            "actionType": "confirm_field",
            "actorType": "human",
            "fieldPath": "medical_eob.total_patient_responsibility",
            "newValue": candidate_id,
            "metadata": {"candidateId": candidate_id},
            "createdAt": "2026-04-26T00:00:00Z",
        },
    )
    assert accepted.status_code == 200

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS total FROM review_events WHERE document_id = %s",
                (document_id,),
            )
            assert cur.fetchone()["total"] >= 1
            cur.execute(
                "SELECT count(*) AS total FROM canonical_fact_history WHERE document_id = %s",
                (document_id,),
            )
            assert cur.fetchone()["total"] >= 1


def _phase4_client(
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
    email = f"phase4-{label}-{unique}@example.com"
    password = "minimum8"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name=f"Phase 4 {label} Admin",
        household_name=f"Phase 4 {label} {unique}",
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
        files={"file": ("phase4.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert accepted.status_code == 202
    listed = client.get("/api/v1/documents", params={"q": title})
    assert listed.status_code == 200
    return uuid.UUID(listed.json()["items"][0]["id"])
