from __future__ import annotations

from lib.extraction.model_output_value_parsing import (
    bounded_text,
    money_value,
    number_value,
    string_values,
    value_type,
)


def test_model_output_value_parsing_preserves_granite_scalar_coercions() -> None:
    assert number_value("$1,234.50") == 1234.5
    assert money_value("$42.10") == {"amount": 42.1, "currency": "USD"}
    assert string_values([" service ", "", None, 25]) == ["service", "None", "25"]
    assert bounded_text("  abcdef  ", max_length=4) == "abcd"
    assert value_type({"raw": "json"}) == "json"
