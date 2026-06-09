from __future__ import annotations

from uuid import UUID, uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_normalization import normalize_granite_region_output
from lib.extraction.region_envelope import envelope_from_normalization_projection


def test_service_record_line_item_model_output_preserves_operation_and_part_codes() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_service_record_line_items.v1",
        payload={
            "line_items": [
                {
                    "ordinal": None,
                    "description": "600 mile running-in check",
                    "service_description": None,
                    "labor_operation": "0000600",
                    "part_number": None,
                    "quantity": "1",
                    "unit": None,
                    "unit_price": "$185.00",
                    "line_total": "$185.00",
                    "amount": None,
                    "category_hint": "service",
                    "row_index": None,
                    "table_id": None,
                    "page_number": None,
                },
                {
                    "ordinal": None,
                    "description": "Hypoid axle oil G3",
                    "service_description": None,
                    "labor_operation": None,
                    "part_number": "33-11-7-695-240",
                    "quantity": "1",
                    "unit": None,
                    "unit_price": None,
                    "line_total": None,
                    "amount": "$21.00",
                    "category_hint": "part",
                    "row_index": None,
                    "table_id": None,
                    "page_number": None,
                },
            ],
            "totals": {"subtotal": None, "tax": None, "total": None},
            "confidence": {"overall": 0.8, "schema_fit": 0.8, "table_structure": 0.8},
        },
        evidence_context=_evidence_context(document_id),
    )

    assert normalized["line_items"][0]["sku"] == "0000600"
    assert normalized["line_items"][1]["sku"] == "33-11-7-695-240"

    envelope = envelope_from_normalization_projection(
        projection=normalized,
        model_output_schema_name="granite_service_record_line_items.v1",
        semantic_type="service_record_line_item_table",
        target_schema="receipt",
        resolved_document_type="service_record",
        source_engine="granite_vision_3b",
    )
    code_claims = [
        claim
        for claim in claims_from_region_envelope(envelope)
        if claim.canonical_key == "service_record.line_item.code"
    ]

    assert [claim.typed_value for claim in code_claims] == [
        "0000600",
        "33-11-7-695-240",
    ]


def test_service_record_flat_output_does_not_create_code_claims() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_service_record_line_items.v1",
        payload={
            "service_description": ["600 mile running-in check"],
            "labor_operation": ["0000600"],
            "part_number": ["33-11-7-695-240"],
            "quantity": ["1", "1"],
            "unit_price": ["185.00", "21.00"],
            "line_total": ["185.00", "21.00"],
            "confidence": {"overall": 0.8, "schema_fit": 0.8, "table_structure": 0.8},
        },
        evidence_context=_evidence_context(document_id),
    )

    assert normalized["line_items"] == []
    assert metadata["rejected_fields"] == [
        "labor_operation",
        "line_total",
        "part_number",
        "quantity",
        "service_description",
        "unit_price",
    ]


def _evidence_context(document_id: UUID) -> EvidenceContext:
    return EvidenceContext(
        source_engine="granite_vision_3b",
        document_id=document_id,
        semantic_annotation_id=uuid4(),
        semantic_region_id=uuid4(),
        page_id=uuid4(),
        page_number=1,
        table_id=uuid4(),
    )
