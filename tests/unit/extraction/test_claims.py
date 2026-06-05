from __future__ import annotations

from uuid import uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)


def test_claims_require_structural_anchor() -> None:
    document_id = uuid4()
    anchored_region_id = uuid4()
    unanchored_region_id = uuid4()
    anchored = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(anchored_region_id),
        resolved_document_type="invoice",
        semantic_type="payment_summary",
        target_schema="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        facts=[
            RegionFact(
                name="invoice.total_amount",
                value={"amount": 42.5, "currency": "USD"},
                value_type="money",
                evidence=[
                    EvidenceRef(
                        document_id=str(document_id),
                        semantic_region_id=str(anchored_region_id),
                        page_number=1,
                        table_id="table-1",
                        row_index=3,
                        source_engine="granite_vision_3b",
                    )
                ],
            )
        ],
    )
    unanchored = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(unanchored_region_id),
        resolved_document_type="invoice",
        semantic_type="payment_summary",
        target_schema="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        facts=[
            RegionFact(
                name="invoice.tax_total",
                value={"amount": 2.5, "currency": "USD"},
                value_type="money",
                evidence=[
                    EvidenceRef(
                        document_id=str(document_id),
                        semantic_region_id=str(unanchored_region_id),
                        source_engine="granite_vision_3b",
                        source_text="Tax $2.50",
                    )
                ],
            )
        ],
    )

    assert [claim.canonical_key for claim in claims_from_region_envelope(anchored)] == [
        "invoice.total_amount"
    ]
    assert claims_from_region_envelope(unanchored) == []


def test_claim_id_ignores_raw_source_payload_noise() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="table-1",
        row_index=3,
        source_engine="granite_vision_3b",
    )

    def envelope(raw_noise: str) -> RegionExtractionEnvelope:
        return RegionExtractionEnvelope(
            document_id=str(document_id),
            semantic_region_id=str(region_id),
            resolved_document_type="invoice",
            semantic_type="payment_summary",
            target_schema="invoice",
            model_output_schema_name="granite_payment_summary.v1",
            facts=[
                RegionFact(
                    name="invoice.total_amount",
                    value={"amount": 42.5, "currency": "USD"},
                    value_type="money",
                    evidence=[evidence],
                    source_payload={"raw_model_text": raw_noise},
                )
            ],
        )

    first = claims_from_region_envelope(envelope("first stochastic phrasing"))[0]
    second = claims_from_region_envelope(envelope("second stochastic phrasing"))[0]

    assert first.claim_id == second.claim_id
    assert first.typed_value == {"amount": 42.5, "currency": "USD"}
    assert first.source_engine == "granite"


def test_claims_reject_qwen_sourced_values() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="table-1",
        row_index=3,
        source_engine="qwen3_vl_8b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="qwen_semantic_manifest.v1",
        facts=[
            RegionFact(
                name="invoice.total_amount",
                value={"amount": 42.5, "currency": "USD"},
                value_type="money",
                evidence=[evidence],
            )
        ],
        line_items=[
            RegionLineItem(
                description="Qwen-planned line item must not become a value Claim",
                net_amount=42.5,
                currency_code="USD",
                evidence=[evidence],
                table_id="table-1",
                row_index=3,
                page_number=1,
            )
        ],
    )

    assert claims_from_region_envelope(envelope) == []


def test_receipt_line_item_claims_use_family_specific_keys() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="receipt-table",
        row_index=2,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="receipt",
        semantic_type="receipt_line_item_table",
        target_schema="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        line_items=[
            RegionLineItem(
                description="USB-C cable",
                quantity=2.0,
                unit_price=9.99,
                net_amount=19.98,
                currency_code="USD",
                evidence=[evidence],
                table_id="receipt-table",
                row_index=2,
                page_number=1,
            )
        ],
    )

    assert [claim.canonical_key for claim in claims_from_region_envelope(envelope)] == [
        "receipt.line_item.description",
        "receipt.line_item.quantity",
        "receipt.line_item.unit_price",
        "receipt.line_item.amount",
    ]


def test_receipt_compatible_service_record_claims_preserve_canonical_family() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="service-table",
        row_index=4,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="service_record",
        semantic_type="service_record_line_item_table",
        target_schema="receipt",
        model_output_schema_name="granite_service_record_line_items.v1",
        line_items=[
            RegionLineItem(
                description="600 mile running-in check",
                quantity=1.0,
                unit_price=185.0,
                net_amount=185.0,
                currency_code="USD",
                category_hint="service",
                evidence=[evidence],
                table_id="service-table",
                row_index=4,
                page_number=1,
            )
        ],
    )

    assert [claim.canonical_key for claim in claims_from_region_envelope(envelope)] == [
        "service_record.line_item.description",
        "service_record.line_item.quantity",
        "service_record.line_item.unit_price",
        "service_record.line_item.amount",
        "service_record.line_item.category_hint",
    ]


def test_receipt_compatible_retail_order_claims_preserve_canonical_family() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=2,
        table_id="order-table",
        row_index=1,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="retail_order",
        semantic_type="retail_order_line_item_table",
        target_schema="receipt",
        model_output_schema_name="granite_retail_order.v1",
        line_items=[
            RegionLineItem(
                description="Replacement charging cable",
                quantity=2.0,
                unit_price=12.5,
                net_amount=25.0,
                currency_code="USD",
                evidence=[evidence],
                table_id="order-table",
                row_index=1,
                page_number=2,
            )
        ],
    )

    assert [claim.canonical_key for claim in claims_from_region_envelope(envelope)] == [
        "retail_order.line_item.description",
        "retail_order.line_item.quantity",
        "retail_order.line_item.unit_price",
        "retail_order.line_item.amount",
    ]
