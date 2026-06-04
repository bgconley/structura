from __future__ import annotations

from lib.extraction.candidate_quality import reject_line_item, reject_observation


def test_rejects_zero_amount_line_without_service_context() -> None:
    rejected, reason = reject_line_item(
        {
            "description": "Generated row",
            "amount": "0.00",
            "gross_amount": None,
            "net_amount": None,
            "unit_price": None,
        }
    )

    assert rejected is True
    assert reason == "zero_amount_without_service_context"


def test_allows_zero_amount_line_with_service_context() -> None:
    rejected, reason = reject_line_item(
        {
            "description": "Headlight adjustment service",
            "amount": "0.00",
            "service_date": "2023-04-25",
        }
    )

    assert rejected is False
    assert reason is None


def test_eob_nonzero_amount_keys_prevent_zero_amount_rejection() -> None:
    rejected, reason = reject_line_item(
        {
            "service_description": "MRI",
            "procedure_code": "70553",
            "billed_amount": {"amount": 1200.0, "currency": "USD"},
            "allowed_amount": {"amount": 800.0, "currency": "USD"},
            "paid_amount": {"amount": 500.0, "currency": "USD"},
            "patient_responsibility": {"amount": 300.0, "currency": "USD"},
        }
    )

    assert rejected is False
    assert reason is None


def test_allows_zero_value_observation() -> None:
    rejected, reason = reject_observation("escrow_balance", 0)

    assert rejected is False
    assert reason is None
