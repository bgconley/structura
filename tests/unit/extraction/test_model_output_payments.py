from __future__ import annotations

from lib.extraction.model_output_payments import invoice_payment_summary_from_payload


def test_model_output_payment_summary_prefers_payment_record_and_metadata_context() -> None:
    summary = invoice_payment_summary_from_payload(
        {
            "invoice": {"invoice_number": "INV-42"},
            "payments": [
                {
                    "amount": "$123.45",
                    "card_number": "****4242",
                    "terminal_id": "TERM-7",
                }
            ],
            "metadata": {
                "payment_summary": {
                    "merchant_id": "MERCHANT-9",
                    "auth_code": "AUTH-1",
                }
            },
            "totals": {"amount_paid": "$120.00"},
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
        },
    }
