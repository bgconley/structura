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
    assert money_value("$42.10") == {"amount": 42.1}
    assert string_values([" service ", "", None, 25]) == ["service", "None", "25"]
    assert bounded_text("  abcdef  ", max_length=4) == "abcd"
    assert value_type({"raw": "json"}) == "json"


def test_money_value_does_not_fabricate_currency() -> None:
    assert money_value("42.10") == {"amount": 42.1}
    assert money_value({"amount": 10}) == {"amount": 10.0}
    assert money_value({"amount": "12.50", "currency": "eur"}) == {
        "amount": 12.5,
        "currency": "EUR",
    }
    assert money_value({"amount": 9.5, "currency_code": "gbp"}) == {
        "amount": 9.5,
        "currency": "GBP",
    }


def test_number_value_parses_accounting_negatives() -> None:
    assert number_value("(125.00)") == -125.0
    assert number_value("($125.00)") == -125.0
    assert number_value("125.00-") == -125.0
    assert number_value("-$125.00") == -125.0
    assert number_value("$-125.00") == -125.0
    assert number_value("-125.00") == -125.0


def test_number_value_parses_locale_separators() -> None:
    assert number_value("1,234.56") == 1234.56
    assert number_value("1.234,56") == 1234.56
    assert number_value("12,34") == 12.34
    assert number_value("1,234") == 1234.0
    assert number_value("1.234.567") == 1234567.0
    assert number_value("12.345,67") == 12345.67
    assert number_value("1,234,567.89") == 1234567.89


def test_number_value_rejects_non_numeric_values() -> None:
    assert number_value(True) is None
    assert number_value("no digits") is None
    assert number_value(None) is None
    assert number_value({"amount": 5}) is None
