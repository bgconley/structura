from __future__ import annotations

from datetime import date

from lib.extraction.candidate_value_parsing import (
    candidate_status,
    confidence_or_none,
    date_value,
    empty_observation_value,
    grid_only_observation,
    money_amount,
    money_currency,
    number_value,
    overall_confidence,
)
from lib.extraction.models import ValidationReport


def test_candidate_value_parsing_handles_dates_numbers_and_observation_noise() -> None:
    assert date_value("Service date: 04/25/23") == date(2023, 4, 25)
    assert date_value("25-Apr-2023") == date(2023, 4, 25)
    assert number_value("total $1,234.56") == 1234.56
    assert confidence_or_none("0.87") == 0.87
    assert confidence_or_none("1.50") is None
    assert money_amount({"amount": "42.75", "currency": "USD"}) == 42.75
    assert money_currency({"amount": 42.75, "currency": "USD"}) == "USD"
    assert overall_confidence({"confidence": {"overall": 0.73}}) == 0.73

    assert empty_observation_value("") is True
    assert empty_observation_value({"value": "present"}) is False
    assert grid_only_observation("dimensions", {"rows": 3, "cols": 4}) is True
    assert grid_only_observation("cells", [[1, 2], [3, 4]]) is True
    assert grid_only_observation("cells", [["Procedure", "Amount"], ["MRI", "$100"]]) is False


def test_candidate_status_is_review_required_for_qwen_review_or_weak_evidence() -> None:
    validation = ValidationReport(needs_review=False, checks=[])
    concrete_evidence = [{"page_number": 1, "element_id": "element-1"}]

    assert (
        candidate_status(validation, concrete_evidence, source_engine="granite_vision_3b")
        == "proposed"
    )
    assert (
        candidate_status(validation, concrete_evidence, source_engine="qwen3_vl_8b")
        == "needs_review"
    )
    assert candidate_status(validation, [], source_engine="granite_vision_3b") == "needs_review"
    assert (
        candidate_status(
            ValidationReport(needs_review=True, checks=[]),
            concrete_evidence,
            source_engine="granite_vision_3b",
        )
        == "needs_review"
    )
