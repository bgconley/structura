"""Validate human-entered typed values before canonical persistence.

Unlike model normalization, corrections must never guess a numeric locale,
truncate an integer, interpret a string as a boolean, or round storage precision.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime
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
    elif value_type == "date":
        _date_value(value)
    elif value_type == "datetime":
        _datetime_value(value)
    elif value_type == "json":
        _validate_json_value(value)


def correction_storage_value(value_type: str, value: object, currency: str | None = None) -> object:
    """Return a validated value in the native type used by canonical persistence."""
    validate_correction_value(value_type, value, currency)
    if value_type == "date":
        return _date_value(value)
    if value_type == "datetime":
        return _datetime_value(value)
    return value


def _date_value(value: object) -> date:
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise CorrectionValueError("Enter a valid calendar date in YYYY-MM-DD format.")


def _datetime_value(value: object) -> datetime:
    # Never infer the reviewer's timezone or let PostgreSQL interpret an ambiguous
    # local time. Microsecond precision is the timestamp column's precision.
    pattern = (
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})"
    )
    if isinstance(value, str) and re.fullmatch(pattern, value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            offset = value[-6:]
            if offset.startswith(("+", "-")) and int(offset[-2:]) >= 60:
                raise ValueError("Invalid timezone offset")
            # RFC3339 -00:00 means the local offset is unknown, not UTC.
            if offset != "-00:00":
                parsed.astimezone(UTC)  # Ensure the stored instant can be read back by Python.
                return parsed
        except (ValueError, OverflowError):
            pass
    raise CorrectionValueError(
        "Enter a valid date and time with seconds and an explicit offset, such as "
        "2026-09-07T14:30:00-04:00; use at most six fractional digits."
    )


def _validate_json_value(value: object, depth: int = 0) -> None:
    if depth > 64:
        raise CorrectionValueError("JSON corrections support at most 64 nested levels.")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_json_value(item, depth + 1)
        return
    raise CorrectionValueError("Enter valid JSON with finite numbers and string object keys.")


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
