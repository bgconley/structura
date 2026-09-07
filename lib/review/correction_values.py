"""Validate human-entered typed values before canonical persistence.

Unlike model normalization, corrections must never guess a numeric locale,
truncate an integer, interpret a string as a boolean, or round storage precision.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal


class CorrectionValueError(ValueError):
    """A safe, user-facing correction validation failure."""


def validate_correction_value(value_type: str, value: object, currency: str | None = None) -> None:
    if value_type not in {
        "string",
        "integer",
        "number",
        "boolean",
        "date",
        "datetime",
        "json",
        "money",
    }:
        raise CorrectionValueError("Unsupported correction value type.")
    if value_type == "money":
        if isinstance(value, dict):
            if set(value) != {"amount", "currency"}:
                raise CorrectionValueError("Money requires an amount and currency only.")
            amount = value["amount"]
            money_currency = value["currency"]
            if currency is not None and currency != money_currency:
                raise CorrectionValueError("Money currency must match the field currency.")
        else:
            amount = value
            money_currency = currency
        if not isinstance(money_currency, str) or not re.fullmatch(r"[A-Z]{3}", money_currency):
            raise CorrectionValueError("Money requires a three-letter uppercase currency code.")
        _validate_decimal(amount)
    elif value_type == "number":
        _validate_decimal(value)
    elif value_type == "integer":
        if type(value) is not int or not -(2**63) <= value < 2**63:
            raise CorrectionValueError("Enter a whole integer within the supported range.")
    elif value_type == "boolean" and type(value) is not bool:
        raise CorrectionValueError("A boolean correction must be true or false.")
    elif value_type == "string" and not isinstance(value, str):
        raise CorrectionValueError("A text correction must be a string.")


def _validate_decimal(value: object) -> None:
    # JSON numbers only: bool is an int subclass, and Decimal('NaN') would
    # otherwise survive conversion into PostgreSQL's numeric type.
    if type(value) not in (int, float) or (isinstance(value, float) and not math.isfinite(value)):
        raise CorrectionValueError("Enter a finite numeric amount without currency or separators.")
    decimal = Decimal(str(value))
    if abs(decimal) >= Decimal("100000000000000"):
        raise CorrectionValueError("The amount exceeds the supported range.")
    if decimal != decimal.quantize(Decimal("0.0001")):
        raise CorrectionValueError("Use at most four decimal places; values are not rounded.")
