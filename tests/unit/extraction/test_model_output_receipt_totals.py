from __future__ import annotations

from uuid import uuid4

from lib.extraction.model_output_normalization import normalize_granite_region_output


def test_receipt_payment_summary_model_output_preserves_discount_total() -> None:
    normalized, _metadata = normalize_granite_region_output(
        document_id=uuid4(),
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload={
            "merchant_name": "Corner Cafe",
            "transaction_date": "2026-06-05",
            "subtotal": "$20.00",
            "tax": "$2.00",
            "tip": "$3.00",
            "discount_total": "$5.00",
            "total": "$20.00",
            "payment_method": None,
            "confidence": {"overall": 0.8, "schema_fit": 0.8},
        },
    )

    assert normalized["transaction"] == {
        "date_local": "2026-06-05",
        "subtotal": {"amount": 20.0},
        "tax": {"amount": 2.0},
        "tip": {"amount": 3.0},
        "discount_total": {"amount": 5.0},
        "total": {"amount": 20.0},
    }
