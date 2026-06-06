from __future__ import annotations

from uuid import uuid4

from lib.extraction.model_output_normalization import normalize_granite_region_output


def test_invoice_line_item_model_output_preserves_total_adjustments() -> None:
    normalized, _metadata = normalize_granite_region_output(
        document_id=uuid4(),
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "line_items": [{"description": "Alignment service", "amount": "$99.00"}],
            "totals": {
                "subtotal": "$100.00",
                "tax_total": "$10.00",
                "shipping_total": "$5.00",
                "discount_total": "$16.00",
                "total": "$99.00",
            },
        },
    )

    assert normalized["line_items"][0]["description"] == "Alignment service"
    assert normalized["totals"] == {
        "subtotal": {"amount": 100.0, "currency": "USD"},
        "tax_total": {"amount": 10.0, "currency": "USD"},
        "shipping_total": {"amount": 5.0, "currency": "USD"},
        "discount_total": {"amount": 16.0, "currency": "USD"},
        "total": {"amount": 99.0, "currency": "USD"},
    }
