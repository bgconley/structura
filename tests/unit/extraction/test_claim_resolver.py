from __future__ import annotations

from typing import cast

from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.claims import Claim, ClaimAnchor, ClaimSourceEngine


def test_invoice_claim_resolver_projects_claims_with_source_precedence() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="table-1", row_index=1)
    docling_total = _claim(
        canonical_key="invoice.total_amount",
        typed_value={"amount": 41.0, "currency": "USD"},
        source_engine="docling",
        anchor=anchor,
    )
    granite_total = _claim(
        canonical_key="invoice.total_amount",
        typed_value={"amount": 42.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    line_description = _claim(
        canonical_key="invoice.line_item.description",
        typed_value="Alignment service",
        source_engine="granite",
        anchor=anchor,
        group_id="line-1",
    )
    line_amount = _claim(
        canonical_key="invoice.line_item.amount",
        typed_value={"amount": 42.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="line-1",
    )

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[docling_total, granite_total, line_description, line_amount],
    )

    assert projection.fields["totals"]["total"] == {"amount": 42.0, "currency": "USD"}
    assert projection.line_items == [
        {
            "description": "Alignment service",
            "amount": {"amount": 42.0, "currency": "USD"},
            "evidence": [{"page_number": 1, "table_id": "table-1", "row_index": 1}],
        }
    ]
    assert [
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    ] == [
        ("invoice.invoice_number", "absent", "required_claim_absent"),
        ("invoice.line_item.amount", "accepted", "single_source"),
        ("invoice.line_item.description", "accepted", "single_source"),
        ("invoice.total_amount", "needs_review", "source_precedence_conflict"),
    ]
    assert projection.quality_outcome == "needs_human_review"


def test_receipt_claim_resolver_projects_registry_fields_and_line_items() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="receipt-table", row_index=2)
    merchant = _claim(
        canonical_key="receipt.merchant.display_name",
        typed_value="Apple Store",
        source_engine="granite",
        anchor=anchor,
    )
    total = _claim(
        canonical_key="receipt.transaction.total",
        typed_value={"amount": 21.63, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    line_description = _claim(
        canonical_key="receipt.line_item.description",
        typed_value="USB-C cable",
        source_engine="granite",
        anchor=anchor,
        group_id="receipt-line-1",
    )
    line_sku = _claim(
        canonical_key="receipt.line_item.code",
        typed_value="MU9F2AM/A",
        source_engine="granite",
        anchor=anchor,
        group_id="receipt-line-1",
    )
    line_amount = _claim(
        canonical_key="receipt.line_item.amount",
        typed_value={"amount": 19.98, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="receipt-line-1",
    )
    unsupported_line_tax = _claim(
        canonical_key="receipt.line_item.tax_amount",
        typed_value={"amount": 1.65, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="receipt-line-1",
    )

    projection = resolve_claims_for_family(
        family="receipt",
        claims=[merchant, total, line_description, line_sku, line_amount, unsupported_line_tax],
    )

    assert projection.fields["merchant"] == {"display_name": "Apple Store"}
    assert projection.fields["transaction"] == {"total": {"amount": 21.63, "currency": "USD"}}
    assert projection.line_items == [
        {
            "description": "USB-C cable",
            "sku": "MU9F2AM/A",
            "amount": {"amount": 19.98, "currency": "USD"},
            "evidence": [{"page_number": 1, "table_id": "receipt-table", "row_index": 2}],
        }
    ]
    assert "receipt.line_item.code" in {decision.canonical_key for decision in projection.decisions}
    assert "receipt.line_item.sku" not in {
        decision.canonical_key for decision in projection.decisions
    }
    assert projection.quality_outcome == "extracted_cleanly"


def test_receipt_claim_resolver_demotes_total_arithmetic_conflicts_to_review() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="receipt-summary", row_index=1)
    subtotal = _claim(
        canonical_key="receipt.transaction.subtotal",
        typed_value={"amount": 10.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    tax = _claim(
        canonical_key="receipt.transaction.tax",
        typed_value={"amount": 1.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    tip = _claim(
        canonical_key="receipt.transaction.tip",
        typed_value={"amount": 2.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    total = _claim(
        canonical_key="receipt.transaction.total",
        typed_value={"amount": 20.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )

    projection = resolve_claims_for_family(
        family="receipt",
        claims=[subtotal, tax, tip, total],
    )

    assert projection.fields["transaction"]["total"] == {"amount": 20.0, "currency": "USD"}
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        ("receipt.transaction.total", "needs_review", "cross_field_arithmetic_conflict"),
    }
    assert projection.quality_outcome == "needs_human_review"


def test_invoice_claim_resolver_demotes_arithmetic_conflicts_to_review() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="totals-table", row_index=1)
    invoice_number = _claim(
        canonical_key="invoice.invoice_number",
        typed_value="INV-42",
        source_engine="granite",
        anchor=anchor,
    )
    subtotal = _claim(
        canonical_key="invoice.subtotal",
        typed_value={"amount": 10.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    tax_total = _claim(
        canonical_key="invoice.tax_total",
        typed_value={"amount": 2.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    total = _claim(
        canonical_key="invoice.total_amount",
        typed_value={"amount": 20.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[invoice_number, subtotal, tax_total, total],
    )

    assert projection.fields["totals"]["total"] == {"amount": 20.0, "currency": "USD"}
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        ("invoice.total_amount", "needs_review", "cross_field_arithmetic_conflict"),
    }
    assert projection.quality_outcome == "needs_human_review"


def test_invoice_claim_resolver_demotes_currency_conflicts_to_review() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="totals-table", row_index=1)
    invoice_number = _claim(
        canonical_key="invoice.invoice_number",
        typed_value="INV-42",
        source_engine="granite",
        anchor=anchor,
    )
    subtotal = _claim(
        canonical_key="invoice.subtotal",
        typed_value={"amount": 10.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    tax_total = _claim(
        canonical_key="invoice.tax_total",
        typed_value={"amount": 2.0, "currency": "EUR"},
        source_engine="granite",
        anchor=anchor,
    )
    total = _claim(
        canonical_key="invoice.total_amount",
        typed_value={"amount": 12.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[invoice_number, subtotal, tax_total, total],
    )

    assert projection.fields["totals"]["total"] == {"amount": 12.0, "currency": "USD"}
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        ("invoice.total_amount", "needs_review", "cross_field_currency_conflict"),
    }
    assert projection.quality_outcome == "needs_human_review"


def test_invoice_claim_resolver_demotes_line_item_sum_conflicts_to_review() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="invoice-table", row_index=1)
    invoice_number = _claim(
        canonical_key="invoice.invoice_number",
        typed_value="INV-42",
        source_engine="granite",
        anchor=anchor,
    )
    subtotal = _claim(
        canonical_key="invoice.subtotal",
        typed_value={"amount": 100.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    first_line = _claim(
        canonical_key="invoice.line_item.amount",
        typed_value={"amount": 40.0, "currency": "USD"},
        source_engine="granite",
        anchor=ClaimAnchor(page_number=1, table_id="invoice-table", row_index=2),
        group_id="line-1",
    )
    second_line = _claim(
        canonical_key="invoice.line_item.amount",
        typed_value={"amount": 30.0, "currency": "USD"},
        source_engine="granite",
        anchor=ClaimAnchor(page_number=1, table_id="invoice-table", row_index=3),
        group_id="line-2",
    )
    total = _claim(
        canonical_key="invoice.total_amount",
        typed_value={"amount": 100.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[invoice_number, subtotal, first_line, second_line, total],
    )

    assert projection.fields["totals"]["subtotal"] == {"amount": 100.0, "currency": "USD"}
    assert [item["amount"] for item in projection.line_items] == [
        {"amount": 40.0, "currency": "USD"},
        {"amount": 30.0, "currency": "USD"},
    ]
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        ("invoice.subtotal", "needs_review", "line_item_sum_conflict"),
    }
    assert projection.quality_outcome == "needs_human_review"


def test_medical_eob_claim_resolver_projects_registry_fields_and_service_lines() -> None:
    anchor = ClaimAnchor(
        page_number=2, table_id="00000000-0000-0000-0000-000000000001", row_index=4
    )
    payer = _claim(
        canonical_key="medical_eob.payer.display_name",
        typed_value="Anthem Blue Cross",
        source_engine="granite",
        anchor=anchor,
    )
    patient = _claim(
        canonical_key="medical_eob.patient.display_name",
        typed_value="Jane Patient",
        source_engine="granite",
        anchor=anchor,
    )
    claim_number = _claim(
        canonical_key="medical_eob.claim_number",
        typed_value="CLM-123",
        source_engine="granite",
        anchor=anchor,
    )
    total_patient_responsibility = _claim(
        canonical_key="medical_eob.total_patient_responsibility",
        typed_value={"amount": 62.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    service_description = _claim(
        canonical_key="medical_eob.line_item.description",
        typed_value="Office visit",
        source_engine="granite",
        anchor=anchor,
        group_id="service-line-1",
    )
    procedure_code = _claim(
        canonical_key="medical_eob.line_item.code",
        typed_value="99213",
        source_engine="granite",
        anchor=anchor,
        group_id="service-line-1",
    )
    units = _claim(
        canonical_key="medical_eob.line_item.quantity",
        typed_value=1.0,
        source_engine="granite",
        anchor=anchor,
        group_id="service-line-1",
    )
    billed_amount = _claim(
        canonical_key="medical_eob.line_item.gross_amount",
        typed_value={"amount": 120.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="service-line-1",
    )
    patient_responsibility = _claim(
        canonical_key="medical_eob.line_item.amount",
        typed_value={"amount": 62.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="service-line-1",
    )

    projection = resolve_claims_for_family(
        family="medical_eob",
        claims=[
            payer,
            patient,
            claim_number,
            total_patient_responsibility,
            service_description,
            procedure_code,
            units,
            billed_amount,
            patient_responsibility,
        ],
    )

    assert projection.family == "medical_eob"
    assert projection.fields["payer"] == {"display_name": "Anthem Blue Cross"}
    assert projection.fields["patient"] == {"display_name": "Jane Patient"}
    assert projection.fields["claim"] == {"claim_number": "CLM-123"}
    assert projection.fields["financial_summary"] == {
        "total_patient_responsibility": {"amount": 62.0, "currency": "USD"}
    }
    assert projection.line_items == [
        {
            "service_description": "Office visit",
            "procedure_code": "99213",
            "units": 1.0,
            "billed_amount": {"amount": 120.0, "currency": "USD"},
            "patient_responsibility": {"amount": 62.0, "currency": "USD"},
            "evidence": [
                {
                    "page_number": 2,
                    "table_id": "00000000-0000-0000-0000-000000000001",
                    "row_index": 4,
                }
            ],
        }
    ]
    assert projection.quality_outcome == "extracted_cleanly"


def test_service_record_claim_resolver_projects_registry_line_items() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="service-table", row_index=3)
    description = _claim(
        canonical_key="service_record.line_item.description",
        typed_value="600 mile running-in check",
        source_engine="granite",
        anchor=anchor,
        group_id="service-record-line-1",
    )
    quantity = _claim(
        canonical_key="service_record.line_item.quantity",
        typed_value=1.0,
        source_engine="granite",
        anchor=anchor,
        group_id="service-record-line-1",
    )
    unit_price = _claim(
        canonical_key="service_record.line_item.unit_price",
        typed_value={"amount": 185.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="service-record-line-1",
    )
    amount = _claim(
        canonical_key="service_record.line_item.amount",
        typed_value={"amount": 185.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="service-record-line-1",
    )
    category_hint = _claim(
        canonical_key="service_record.line_item.category_hint",
        typed_value="service",
        source_engine="granite",
        anchor=anchor,
        group_id="service-record-line-1",
    )

    projection = resolve_claims_for_family(
        family="service_record",
        claims=[description, quantity, unit_price, amount, category_hint],
    )

    assert projection.family == "service_record"
    assert projection.line_items == [
        {
            "description": "600 mile running-in check",
            "quantity": 1.0,
            "unit_price": {"amount": 185.0, "currency": "USD"},
            "amount": {"amount": 185.0, "currency": "USD"},
            "category_hint": "service",
            "evidence": [{"page_number": 1, "table_id": "service-table", "row_index": 3}],
        }
    ]
    assert projection.quality_outcome == "extracted_cleanly"


def test_retail_order_claim_resolver_projects_registry_fields_and_line_items() -> None:
    anchor = ClaimAnchor(page_number=2, table_id="order-table", row_index=1)
    merchant = _claim(
        canonical_key="retail_order.merchant_name",
        typed_value="Acme Parts",
        source_engine="granite",
        anchor=anchor,
    )
    order_number = _claim(
        canonical_key="retail_order.order_number",
        typed_value="ORDER-123",
        source_engine="granite",
        anchor=anchor,
    )
    total = _claim(
        canonical_key="retail_order.total",
        typed_value={"amount": 25.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    description = _claim(
        canonical_key="retail_order.line_item.description",
        typed_value="Replacement charging cable",
        source_engine="granite",
        anchor=anchor,
        group_id="retail-order-line-1",
    )
    quantity = _claim(
        canonical_key="retail_order.line_item.quantity",
        typed_value=2.0,
        source_engine="granite",
        anchor=anchor,
        group_id="retail-order-line-1",
    )
    unit_price = _claim(
        canonical_key="retail_order.line_item.unit_price",
        typed_value={"amount": 12.5, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="retail-order-line-1",
    )
    amount = _claim(
        canonical_key="retail_order.line_item.amount",
        typed_value={"amount": 25.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="retail-order-line-1",
    )

    projection = resolve_claims_for_family(
        family="retail_order",
        claims=[merchant, order_number, total, description, quantity, unit_price, amount],
    )

    assert projection.family == "retail_order"
    assert projection.fields["order"] == {
        "merchant_name": "Acme Parts",
        "order_number": "ORDER-123",
    }
    assert projection.fields["totals"] == {"total": {"amount": 25.0, "currency": "USD"}}
    assert projection.line_items == [
        {
            "description": "Replacement charging cable",
            "quantity": 2.0,
            "unit_price": {"amount": 12.5, "currency": "USD"},
            "amount": {"amount": 25.0, "currency": "USD"},
            "evidence": [{"page_number": 2, "table_id": "order-table", "row_index": 1}],
        }
    ]
    assert projection.quality_outcome == "extracted_cleanly"


def test_document_observation_claim_resolver_projects_claims_to_observations() -> None:
    anchor = ClaimAnchor(page_number=3, page_id="page-3", docling_element_ids=("el-9",))
    docling_address = _claim(
        canonical_key="real_estate_title.property.address",
        typed_value="123 Main",
        source_engine="docling",
        anchor=anchor,
    )
    granite_address = _claim(
        canonical_key="real_estate_title.property.address",
        typed_value="123 Main St",
        source_engine="granite",
        anchor=anchor,
    )

    projection = resolve_claims_for_family(
        family="document_observation",
        claims=[docling_address, granite_address],
    )

    assert projection.family == "document_observation"
    assert projection.observations == [
        {
            "family": "real_estate_title",
            "field_name": "property.address",
            "value": "123 Main St",
            "value_type": "string",
            "source_text": "123 Main St",
            "confidence": 0.9,
            "evidence": [
                {
                    "page_number": 3,
                    "page_id": "page-3",
                    "docling_element_ids": ["el-9"],
                }
            ],
        }
    ]
    assert [
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    ] == [
        (
            "real_estate_title.property.address",
            "needs_review",
            "source_precedence_conflict",
        )
    ]
    assert projection.quality_outcome == "needs_human_review"


def test_unknown_claim_family_degrades_to_document_observation_projection() -> None:
    anchor = ClaimAnchor(page_number=1, text_span={"start": 10, "end": 22})
    claim = _claim(
        canonical_key="mortgage_escrow_statement.shortage_amount",
        typed_value={"amount": 84.25, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )

    projection = resolve_claims_for_family(
        family="mortgage_escrow_statement",
        claims=[claim],
    )

    assert projection.family == "document_observation"
    assert projection.observations == [
        {
            "family": "mortgage_escrow_statement",
            "field_name": "shortage_amount",
            "value": {"amount": 84.25, "currency": "USD"},
            "value_type": "json",
            "source_text": "{'amount': 84.25, 'currency': 'USD'}",
            "confidence": 0.9,
            "evidence": [{"page_number": 1, "text_span": {"start": 10, "end": 22}}],
        }
    ]
    assert projection.quality_outcome == "needs_human_review"


def test_claim_resolver_emits_insufficient_signal_without_usable_claims() -> None:
    projection = resolve_claims_for_family(
        family="invoice",
        claims=[],
    )

    assert projection.fields == {}
    assert projection.line_items == []
    assert projection.quality_outcome == "insufficient_signal"


def test_claim_resolver_records_absent_required_invoice_keys() -> None:
    line_description = _claim(
        canonical_key="invoice.line_item.description",
        typed_value="Anchored labor",
        source_engine="granite",
        anchor=ClaimAnchor(page_number=1, table_id="table-1", row_index=1),
        group_id="line-1",
    )

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[line_description],
    )

    assert projection.line_items == [
        {
            "description": "Anchored labor",
            "evidence": [{"page_number": 1, "table_id": "table-1", "row_index": 1}],
        }
    ]
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        ("invoice.invoice_number", "absent", "required_claim_absent"),
        ("invoice.total_amount", "absent", "required_claim_absent"),
    }
    assert projection.quality_outcome == "needs_human_review"


def test_claim_resolver_ignores_qwen_value_claims() -> None:
    qwen_total = _claim(
        canonical_key="invoice.total_amount",
        typed_value={"amount": 42.0, "currency": "USD"},
        source_engine=cast(ClaimSourceEngine, "qwen"),
        anchor=ClaimAnchor(page_number=1, table_id="table-1", row_index=1),
    )

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[qwen_total],
    )

    assert projection.fields == {}
    assert [
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    ] == [
        ("invoice.invoice_number", "absent", "required_claim_absent"),
        ("invoice.total_amount", "absent", "required_claim_absent"),
    ]
    assert projection.quality_outcome == "insufficient_signal"


def _claim(
    *,
    canonical_key: str,
    typed_value: object,
    source_engine: ClaimSourceEngine,
    anchor: ClaimAnchor,
    group_id: str | None = None,
) -> Claim:
    return Claim(
        claim_id=f"{source_engine}:{canonical_key}:{typed_value}",
        document_id="doc-1",
        source_engine=source_engine,
        anchor=anchor,
        canonical_key=canonical_key,
        raw_value=str(typed_value),
        typed_value=typed_value,
        value_type="money" if isinstance(typed_value, dict) else "text",
        confidence=0.9,
        method="test",
        group_id=group_id,
        evidence=(anchor.as_json(),),
    )
