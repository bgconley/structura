from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.claim_projection import project_claim_family_payload
from lib.extraction.claim_resolver import ClaimFamilyProjection


def test_registry_projection_builds_medical_eob_payload_shape() -> None:
    document_id = uuid4()
    created_at = datetime.now(UTC)
    projection = ClaimFamilyProjection(
        family="medical_eob",
        fields={
            "payer": {"display_name": "Anthem Blue Cross"},
            "patient": {"display_name": "Jane Patient"},
            "provider": {},
            "claim": {"claim_number": "CLM-123"},
            "financial_summary": {
                "total_patient_responsibility": {"amount": 62.0, "currency": "USD"}
            },
        },
        line_items=[
            {
                "service_description": "Office visit",
                "patient_responsibility": {"amount": 62.0, "currency": "USD"},
                "evidence": [{"page_number": 2, "table_id": "eob-table", "row_index": 4}],
            }
        ],
    )

    payload = project_claim_family_payload(
        document_id=document_id,
        created_at=created_at,
        projection=projection,
        metadata={"quality_outcome": "extracted_cleanly"},
    )

    assert payload == {
        "schema_name": "medical_eob",
        "schema_version": "v1",
        "document_id": str(document_id),
        "payer": {"display_name": "Anthem Blue Cross"},
        "patient": {"display_name": "Jane Patient"},
        "claim": {"claim_number": "CLM-123"},
        "service_lines": [
            {
                "service_description": "Office visit",
                "patient_responsibility": {"amount": 62.0, "currency": "USD"},
                "evidence": [{"page_number": 2, "table_id": "eob-table", "row_index": 4}],
                "ordinal": 1,
            }
        ],
        "financial_summary": {"total_patient_responsibility": {"amount": 62.0, "currency": "USD"}},
        "validation": {"needs_review": True, "checks": []},
        "created_at": created_at.isoformat(),
        "metadata": {"quality_outcome": "extracted_cleanly"},
    }


def test_registry_projection_returns_none_for_empty_family_projection() -> None:
    payload = project_claim_family_payload(
        document_id=uuid4(),
        created_at=datetime.now(UTC),
        projection=ClaimFamilyProjection(family="medical_eob"),
        metadata={},
    )

    assert payload is None
