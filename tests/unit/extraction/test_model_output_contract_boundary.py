from __future__ import annotations

from uuid import uuid4

from lib.extraction.model_output_normalization import normalize_granite_region_output


def test_invoice_payment_summary_ignores_off_contract_alias_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        payload={
            "payments": [],
            "invoice_number": "OFF-CONTRACT-INV",
            "totals": {"amount_paid": "$42.00"},
            "confidence": {"overall": 0.61},
        },
    )

    assert normalized["invoice"] == {}
    assert normalized["totals"] == {}
    assert metadata["rejected_fields"] == ["invoice_number", "totals"]


def test_invoice_line_items_ignore_off_contract_total_amount_alias() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "line_items": [],
            "total_amount": "$99.00",
            "confidence": {"overall": 0.61},
        },
    )

    assert "totals" not in normalized
    assert metadata["rejected_fields"] == ["total_amount"]


def test_receipt_payment_summary_ignores_off_contract_merchant_alias() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload={
            "merchant": "Alias Coffee",
            "total": "$4.65",
            "confidence": {"overall": 0.61},
        },
    )

    assert normalized["merchant"] == {}
    assert normalized["transaction"]["total"] == {"amount": 4.65, "currency": "USD"}
    assert metadata["rejected_fields"] == ["merchant"]


def test_line_item_contract_boundary_reports_nested_off_contract_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        payload={
            "line_items": [
                {
                    "description": "Coffee",
                    "amount": "$4.65",
                    "service_description": "Off-contract alias",
                }
            ],
            "confidence": {"overall": 0.61},
        },
    )

    assert normalized["line_items"] == []
    assert metadata["rejected_fields"] == ["line_items[0].service_description"]


def test_schema_invalid_contract_payload_does_not_mine_allowed_sibling_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "totals": {"total": "$99.00"},
            "confidence": {"overall": 0.61},
        },
    )

    assert normalized["line_items"] == []
    assert "totals" not in normalized
    assert metadata["model_output_contract_errors"] == ["$: 'line_items' is a required property"]
    assert "model_output_contract_validation_failed" in metadata["repairs"]
