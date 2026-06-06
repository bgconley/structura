from __future__ import annotations

from uuid import uuid4

from lib.extraction.model_output_normalization import normalize_granite_region_output


def test_receipt_line_item_model_output_preserves_unit_discount_and_tax_hint() -> None:
    normalized, _metadata = normalize_granite_region_output(
        document_id=uuid4(),
        schema_name="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        payload={
            "line_items": [
                {
                    "description": "Coffee beans",
                    "quantity": "2",
                    "unit": "bag",
                    "unit_price": "$12.00",
                    "discount": "$3.00",
                    "amount": "$21.00",
                    "sku": "BEANS-12",
                    "tax_category_hint": "grocery",
                }
            ],
        },
    )

    assert normalized["line_items"] == [
        {
            "ordinal": 1,
            "description": "Coffee beans",
            "quantity": 2.0,
            "unit": "bag",
            "unit_price": {"amount": 12.0, "currency": "USD"},
            "discount": {"amount": 3.0, "currency": "USD"},
            "amount": {"amount": 21.0, "currency": "USD"},
            "sku": "BEANS-12",
            "tax_category_hint": "grocery",
            "evidence": [
                {
                    "source_text": "Coffee beans",
                    "source_engine": "granite_vision_3b",
                    "confidence": 0.72,
                }
            ],
        }
    ]
