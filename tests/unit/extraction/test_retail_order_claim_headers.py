from __future__ import annotations

from uuid import UUID, uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_normalization import normalize_granite_region_output
from lib.extraction.region_envelope import envelope_from_normalization_projection


def test_retail_order_model_output_preserves_header_claims() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_retail_order.v1",
        payload={
            "merchant_name": "Acme Parts",
            "order_number": "ORDER-123",
            "order_date": "2026-05-01",
            "total": "$25.00",
            "line_items": [
                {
                    "description": "Replacement charging cable",
                    "quantity": "2",
                    "unit_price": "$12.50",
                    "amount": "$25.00",
                }
            ],
        },
        evidence_context=_evidence_context(document_id),
    )

    envelope = envelope_from_normalization_projection(
        projection=normalized,
        model_output_schema_name="granite_retail_order.v1",
        semantic_type="retail_order_line_item_table",
        target_schema="receipt",
        resolved_document_type="retail_order",
        source_engine="granite_vision_3b",
    )
    claims_by_key = {
        claim.canonical_key: claim.typed_value for claim in claims_from_region_envelope(envelope)
    }

    assert claims_by_key == {
        "retail_order.merchant_name": "Acme Parts",
        "retail_order.order_number": "ORDER-123",
        "retail_order.order_date": "2026-05-01",
        "retail_order.total": {"amount": 25.0, "currency": "USD"},
        "retail_order.line_item.description": "Replacement charging cable",
        "retail_order.line_item.quantity": 2.0,
        "retail_order.line_item.unit_price": {"amount": 12.5, "currency": "USD"},
        "retail_order.line_item.amount": {"amount": 25.0, "currency": "USD"},
    }


def _evidence_context(document_id: UUID) -> EvidenceContext:
    return EvidenceContext(
        source_engine="granite_vision_3b",
        document_id=document_id,
        semantic_annotation_id=uuid4(),
        semantic_region_id=uuid4(),
        page_id=uuid4(),
        page_number=2,
        table_id=uuid4(),
    )
