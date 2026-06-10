from __future__ import annotations

from uuid import uuid4

from lib.documents.read_model import (
    _extraction_payload,
    _semantic_region_extraction_payload,
)


def _aggregate_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": uuid4(),
        "schema_name": "invoice",
        "schema_version": "v1",
        "status": "completed",
        "source_engine": "system",
        "model_name": "phase8_5-region-reconciler",
        "model_version": "v1",
        "confidence": 0.74,
        "review_status": "needs_review",
        "extraction_scope": "aggregate",
        "quality_outcome": "needs_human_review",
        "aggregate_metadata": {
            "quality_outcome": "needs_human_review",
            "claim_resolution_decisions": [
                {
                    "canonical_key": "invoice.total_amount",
                    "decision": "needs_review",
                    "reason_code": "cross_field_arithmetic_conflict",
                    "selected_claim_id": "claim-1",
                    "rejected_claim_ids": ["claim-2"],
                },
                {
                    "canonical_key": "invoice.invoice_number",
                    "decision": "accepted",
                    "reason_code": "single_source",
                    "selected_claim_id": None,
                    "rejected_claim_ids": [],
                },
            ],
            "region_job_coverage": {"expected": 3, "completed": 3},
            "source_families": ["invoice"],
        },
        "created_at": "2026-06-09T00:00:00Z",
    }
    row.update(overrides)
    return row


def test_aggregate_extraction_payload_exposes_quality_outcome_and_decisions() -> None:
    payload = _extraction_payload(_aggregate_row())

    assert payload["qualityOutcome"] == "needs_human_review"
    decisions = payload["claimResolutionDecisions"]
    assert decisions == [
        {
            "canonicalKey": "invoice.total_amount",
            "decision": "needs_review",
            "reasonCode": "cross_field_arithmetic_conflict",
            "selectedClaimId": "claim-1",
            "rejectedClaimIds": ["claim-2"],
        },
        {
            "canonicalKey": "invoice.invoice_number",
            "decision": "accepted",
            "reasonCode": "single_source",
        },
    ]
    assert payload["regionJobCoverage"] == {"expected": 3, "completed": 3}
    assert payload["sourceFamilies"] == ["invoice"]


def test_extraction_payload_keeps_null_quality_outcome_for_plain_rows() -> None:
    payload = _extraction_payload(
        _aggregate_row(
            extraction_scope="document",
            quality_outcome=None,
            aggregate_metadata=None,
        )
    )

    assert payload["qualityOutcome"] is None
    assert "claimResolutionDecisions" not in payload
    assert "regionJobCoverage" not in payload


def test_semantic_region_payload_does_not_grow_quality_decision_keys() -> None:
    row = {
        "id": uuid4(),
        "schema_name": "invoice",
        "schema_version": "v1",
        "status": "completed",
        "source_engine": "granite_vision_3b",
        "model_name": "granite",
        "model_version": "v1",
        "confidence": None,
        "review_status": "needs_review",
        "extraction_scope": "semantic_region",
        "semantic_annotation_id": uuid4(),
        "source_semantic_region_id": uuid4(),
        "semantic_type": "invoice_line_item_table",
        "granite_task": "tables_json",
        "model_output_schema_name": "granite_invoice_line_items.v1",
        "model_output_schema_version": "v1",
        "normalized_json": {},
        "normalization_json": {},
        "metadata_json": {},
        "created_at": "2026-06-09T00:00:00Z",
    }

    payload = _semantic_region_extraction_payload(row)

    assert payload["semanticType"] == "invoice_line_item_table"
    assert payload["graniteTask"] == "tables_json"
    assert "qualityOutcome" not in payload
