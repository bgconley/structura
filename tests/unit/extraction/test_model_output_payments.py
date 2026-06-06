from __future__ import annotations

from lib.extraction.model_output_payments import invoice_payment_summary_from_payload


def test_model_output_payment_summary_uses_contracted_payment_record_fields() -> None:
    summary = invoice_payment_summary_from_payload(
        {
            "invoice_no": "INV-42",
            "payments": [
                {
                    "amount": "$123.45",
                    "card_number": "****4242",
                    "merchant_id": "MERCHANT-9",
                    "terminal_id": "TERM-7",
                    "auth_code": "AUTH-1",
                    "auth_mode": "MANUAL",
                    "application_name": "Visa",
                }
            ],
        }
    )

    assert summary == {
        "invoice_number": "INV-42",
        "amount_paid": {"amount": 123.45, "currency": "USD"},
        "payment_summary": {
            "card_number": "****4242",
            "merchant_id": "MERCHANT-9",
            "terminal_id": "TERM-7",
            "auth_code": "AUTH-1",
            "auth_mode": "MANUAL",
            "application_name": "Visa",
        },
    }
