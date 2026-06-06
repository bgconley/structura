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


def test_claim_id_canonicalizes_docling_element_id_order() -> None:
    document_id = uuid4()
    region_id = uuid4()

    def envelope(element_id: str) -> RegionExtractionEnvelope:
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
                    evidence=[
                        EvidenceRef(
                            document_id=str(document_id),
                            semantic_region_id=str(region_id),
                            page_number=1,
                            element_id=element_id,
                            table_id="table-1",
                            row_index=3,
                            source_engine="granite_vision_3b",
                        )
                    ],
                )
            ],
        )

    first = claims_from_region_envelope(envelope("cell-b,cell-a"))[0]
    second = claims_from_region_envelope(envelope("cell-a,cell-b"))[0]

    assert first.claim_id == second.claim_id
    assert first.anchor.docling_element_ids == ("cell-a", "cell-b")
    assert second.anchor.docling_element_ids == ("cell-a", "cell-b")


def test_claim_source_uses_granite_method_for_docling_anchor_evidence() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="table-1",
        row_index=3,
        source_engine="docling",
    )
    envelope = RegionExtractionEnvelope(
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
            )
        ],
    )

    claims = claims_from_region_envelope(envelope)

    assert len(claims) == 1
    assert claims[0].source_engine == "granite"


def test_invoice_total_adjustment_claims_are_admissible() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="invoice-totals",
        row_index=1,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        facts=[
            RegionFact(
                name="invoice.shipping_total",
                value={"amount": 5.0, "currency": "USD"},
                value_type="money",
                evidence=[evidence],
            ),
            RegionFact(
                name="invoice.discount_total",
                value={"amount": 15.0, "currency": "USD"},
                value_type="money",
                evidence=[evidence],
            ),
        ],
    )

    claims = claims_from_region_envelope(envelope)

    assert [claim.canonical_key for claim in claims] == [
        "invoice.shipping_total",
        "invoice.discount_total",
    ]
    assert {claim.canonical_key: claim.typed_value for claim in claims} == {
        "invoice.shipping_total": {"amount": 5.0, "currency": "USD"},
        "invoice.discount_total": {"amount": 15.0, "currency": "USD"},
    }


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


def test_claims_reject_qwen_planner_method_with_docling_evidence() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="table-1",
        row_index=3,
        source_engine="docling",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="payment_summary",
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
    )

    assert claims_from_region_envelope(envelope) == []


def test_claims_drop_unknown_registered_family_keys() -> None:
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
    envelope = RegionExtractionEnvelope(
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
            ),
            RegionFact(
                name="invoice.schema_name",
                value="invoice",
                value_type="string",
                evidence=[evidence],
            ),
        ],
    )

    assert [claim.canonical_key for claim in claims_from_region_envelope(envelope)] == [
        "invoice.total_amount"
    ]


def test_claims_drop_registered_field_values_with_wrong_type() -> None:
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
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="payment_summary",
        target_schema="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        facts=[
            RegionFact(
                name="invoice.total_amount",
                value="$42.50",
                value_type="string",
                evidence=[evidence],
            ),
            RegionFact(
                name="invoice.invoice_number",
                value="INV-42",
                value_type="string",
                evidence=[evidence],
            ),
        ],
    )

    assert [claim.canonical_key for claim in claims_from_region_envelope(envelope)] == [
        "invoice.invoice_number"
    ]


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


def test_line_item_group_id_uses_structural_row_anchor_before_model_ordinal() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="invoice-table",
        row_index=3,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        line_items=[
            RegionLineItem(
                description="PERFORM 600 MILE RUNNING-IN CHECK",
                net_amount=250.0,
                currency_code="USD",
                evidence=[evidence],
                table_id="invoice-table",
                row_index=3,
                page_number=1,
            ),
            RegionLineItem(
                description="perform 600 mile running-in check",
                net_amount=250.0,
                currency_code="USD",
                evidence=[evidence],
                table_id="invoice-table",
                row_index=3,
                page_number=1,
            ),
        ],
    )

    line_description_claims = [
        claim
        for claim in claims_from_region_envelope(envelope)
        if claim.canonical_key == "invoice.line_item.description"
    ]

    assert len(line_description_claims) == 2
    assert {claim.group_id for claim in line_description_claims} == {
        line_description_claims[0].group_id
    }


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


def test_medical_eob_line_item_claims_preserve_allowed_and_plan_paid_amounts() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=2,
        table_id="eob-table",
        row_index=4,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="medical_eob",
        semantic_type="covered_services_line_item_table",
        target_schema="medical_eob",
        model_output_schema_name="granite_medical_service_lines.v1",
        line_items=[
            RegionLineItem(
                description="Office visit",
                code="99213",
                gross_amount=120.0,
                allowed_amount=80.0,
                plan_paid_amount=50.0,
                net_amount=30.0,
                currency_code="USD",
                evidence=[evidence],
                table_id="eob-table",
                row_index=4,
                page_number=2,
            )
        ],
    )

    claims = claims_from_region_envelope(envelope)

    assert [claim.canonical_key for claim in claims] == [
        "medical_eob.line_item.description",
        "medical_eob.line_item.code",
        "medical_eob.line_item.gross_amount",
        "medical_eob.line_item.allowed_amount",
        "medical_eob.line_item.plan_paid",
        "medical_eob.line_item.amount",
    ]
    assert {claim.canonical_key: claim.typed_value for claim in claims} == {
        "medical_eob.line_item.description": "Office visit",
        "medical_eob.line_item.code": "99213",
        "medical_eob.line_item.gross_amount": {"amount": 120.0, "currency": "USD"},
        "medical_eob.line_item.allowed_amount": {"amount": 80.0, "currency": "USD"},
        "medical_eob.line_item.plan_paid": {"amount": 50.0, "currency": "USD"},
        "medical_eob.line_item.amount": {"amount": 30.0, "currency": "USD"},
    }


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
