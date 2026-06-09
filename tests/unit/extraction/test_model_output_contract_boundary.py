from __future__ import annotations

from uuid import uuid4

from lib.extraction.model_output_normalization import normalize_granite_region_output


def test_invoice_payment_summary_fails_closed_on_off_contract_alias_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        payload={
            "invoice_no": "INV-1",
            "amount": "$42.00",
            "payments": [
                {
                    "amount": "$42.00",
                    "card_number": None,
                    "merchant_id": None,
                    "terminal_id": None,
                    "auth_code": None,
                    "auth_mode": None,
                    "application_name": None,
                    "source_text": "Paid $42.00",
                }
            ],
            "invoice_number": "OFF-CONTRACT-INV",
            "confidence": {"overall": 0.61, "schema_fit": 0.7},
        },
    )

    assert normalized["invoice"] == {}
    assert normalized["totals"] == {}
    assert normalized["metadata"] == {}
    assert metadata["rejected_fields"] == ["invoice_number"]
    assert any(
        "Additional properties are not allowed" in error
        for error in metadata["model_output_contract_errors"]
    )
    assert "model_output_contract_validation_failed" in metadata["repairs"]


def test_invoice_line_items_fail_closed_on_off_contract_total_amount_alias() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "line_items": [],
            "total_amount": "$99.00",
            "totals": {
                "subtotal": None,
                "tax_total": None,
                "shipping_total": None,
                "discount_total": None,
                "total": "$99.00",
            },
            "confidence": {"overall": 0.61, "schema_fit": 0.7, "table_structure": 0.8},
        },
    )

    assert normalized["line_items"] == []
    assert "totals" not in normalized
    assert metadata["rejected_fields"] == ["total_amount"]
    assert any(
        "Additional properties are not allowed" in error
        for error in metadata["model_output_contract_errors"]
    )
    assert "model_output_contract_validation_failed" in metadata["repairs"]


def test_receipt_payment_summary_fails_closed_on_off_contract_merchant_alias() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload={
            "merchant_name": "Alias Coffee",
            "merchant": "Alias Coffee",
            "transaction_date": None,
            "subtotal": None,
            "tax": None,
            "tip": None,
            "discount_total": None,
            "total": "$4.65",
            "payment_method": None,
            "confidence": {"overall": 0.61, "schema_fit": 0.7},
        },
    )

    assert normalized["merchant"] == {}
    assert normalized["transaction"] == {}
    assert metadata["rejected_fields"] == ["merchant"]
    assert any(
        "Additional properties are not allowed" in error
        for error in metadata["model_output_contract_errors"]
    )
    assert "model_output_contract_validation_failed" in metadata["repairs"]


def test_line_item_contract_boundary_fails_closed_on_nested_off_contract_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        payload={
            "line_items": [
                {
                    "ordinal": 1,
                    "description": "Coffee",
                    "quantity": None,
                    "unit": None,
                    "unit_price": None,
                    "amount": "$4.65",
                    "category_hint": None,
                    "row_index": None,
                    "table_id": None,
                    "page_number": 1,
                    "service_description": "Off-contract alias",
                }
            ],
            "confidence": {"overall": 0.61, "schema_fit": 0.7, "table_structure": 0.8},
        },
    )

    assert normalized["line_items"] == []
    assert metadata["rejected_fields"] == ["line_items[0].service_description"]
    assert any(
        "Additional properties are not allowed" in error
        for error in metadata["model_output_contract_errors"]
    )
    assert "model_output_contract_validation_failed" in metadata["repairs"]


def test_contract_boundary_rejects_missing_required_nullable_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "line_items": [],
            "totals": {
                "subtotal": None,
                "tax_total": None,
                "shipping_total": None,
                "discount_total": None,
                "total": "$99.00",
            },
        },
    )

    assert normalized["line_items"] == []
    assert "totals" not in normalized
    assert metadata["model_output_contract_errors"] == ["$: 'confidence' is a required property"]
    assert "model_output_contract_validation_failed" in metadata["repairs"]


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
    assert "$: 'line_items' is a required property" in metadata["model_output_contract_errors"]
    assert (
        "$.confidence: 'schema_fit' is a required property"
        in metadata["model_output_contract_errors"]
    )
    assert "model_output_contract_validation_failed" in metadata["repairs"]
