from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import ValidationReport
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)
from lib.extraction.region_envelope_candidates import (
    field_candidates_from_region_envelope,
    line_item_candidates_from_region_envelope,
    observation_candidates_from_region_envelope,
)


def test_region_envelope_field_candidates_use_claims_not_normalized_projection() -> None:
    document_id = uuid4()
    region_id = uuid4()
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="payment_summary",
        target_schema="invoice",
        model_output_schema_name="granite_invoice_payment_summary.v1",
        coverage={
            "normalized_projection": {
                "schema_name": "invoice",
                "invoice": {"invoice_number": "RAW-FALLBACK"},
            }
        },
        facts=[
            RegionFact(
                name="invoice.invoice_number",
                value="CLAIM-42",
                value_type="string",
                evidence=[_evidence(document_id, region_id, element_id="el-1")],
            )
        ],
    )

    candidates = field_candidates_from_region_envelope(
        document_id=document_id,
        envelope=envelope,
        validation=ValidationReport(needs_review=False, checks=[]),
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    assert [(candidate.field_path, candidate.value) for candidate in candidates] == [
        ("invoice.invoice_number", "CLAIM-42")
    ]


def test_region_envelope_line_item_candidates_use_claims_not_normalized_projection() -> None:
    document_id = uuid4()
    region_id = uuid4()
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        coverage={
            "normalized_projection": {
                "schema_name": "invoice",
                "line_items": [
                    {
                        "description": "Raw fallback service",
                        "amount": {"amount": 999.0, "currency": "USD"},
                    }
                ],
            }
        },
        line_items=[
            RegionLineItem(
                description="Claim-derived service",
                net_amount=42.0,
                currency_code="USD",
                evidence=[_evidence(document_id, region_id, table_id="table-1", row_index=1)],
                table_id="table-1",
                row_index=1,
                page_number=1,
            )
        ],
    )

    candidates = line_item_candidates_from_region_envelope(
        envelope=envelope,
        validation=ValidationReport(needs_review=False, checks=[]),
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    assert [(candidate.description, candidate.net_amount) for candidate in candidates] == [
        ("Claim-derived service", 42.0)
    ]


def test_alias_region_envelope_candidates_project_to_observations_from_claims() -> None:
    document_id = uuid4()
    region_id = uuid4()
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="service_record",
        semantic_type="service_record_line_item_table",
        target_schema="receipt",
        model_output_schema_name="granite_service_record_line_items.v1",
        coverage={
            "normalized_projection": {
                "schema_name": "receipt",
                "line_items": [{"description": "Receipt-shaped fallback"}],
            }
        },
        line_items=[
            RegionLineItem(
                description="600 mile running-in check",
                net_amount=185.0,
                currency_code="USD",
                evidence=[_evidence(document_id, region_id, table_id="service-table", row_index=2)],
                table_id="service-table",
                row_index=2,
                page_number=1,
            )
        ],
    )

    candidates = observation_candidates_from_region_envelope(
        envelope=envelope,
        validation=ValidationReport(needs_review=False, checks=[]),
        require_concrete_evidence=True,
    )

    by_field = {candidate.field_name: candidate for candidate in candidates}
    assert by_field["line_item.description"].observation_family == "service_record"
    assert by_field["line_item.description"].value == "600 mile running-in check"
    assert by_field["line_item.amount"].value == {"amount": 185.0, "currency": "USD"}


def _evidence(
    document_id,
    semantic_region_id,
    *,
    element_id: str | None = None,
    table_id: str | None = None,
    row_index: int | None = None,
) -> EvidenceRef:
    return EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(semantic_region_id),
        page_number=1,
        element_id=element_id,
        table_id=table_id,
        row_index=row_index,
        source_engine="granite_vision_3b",
    )
