"""Immutable recorded-text-exact-v1 typing of a recorded transcription slice.

Future typing rules require a new version dispatcher; do not reinterpret retained
v1 claims by changing these normalization semantics.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lib.extraction.native_claims.errors import NativeClaimError

NativeValueType = Literal[
    "money", "date", "quantity", "identifier", "party", "enum", "text", "number", "boolean"
]
DECIMAL = re.compile(r"[+-]?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


class NativeMoney(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    amount: str
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


def exact_decimal(value: str) -> str:
    if not DECIMAL.fullmatch(value):
        raise NativeClaimError("Recorded source value does not satisfy exact decimal typing.")
    digits = value.lstrip("+-").replace(".", "")
    if len(digits) > 38 or ("." in value and len(value.partition(".")[2]) > 12):
        raise NativeClaimError("Recorded decimal exceeds the native claim typing bound.")
    return format(Decimal(value), "f")


def type_recorded_text(value_type: NativeValueType, source_text: str) -> str | bool | NativeMoney:
    """No locale guessing, inferred currency, float coercion or model-valued override."""
    value = source_text.strip()
    if not value or len(value) > 4096:
        raise NativeClaimError("Recorded source value is empty or exceeds the typing bound.")
    if value_type in {"number", "quantity"}:
        return exact_decimal(value)
    if value_type == "money":
        # Only an explicit three-letter source code supplies currency. Symbols are
        # not silently interpreted as USD, and ambiguous formatting is rejected.
        match = re.fullmatch(
            r"(?:(?P<leading>[A-Z]{3}) )?(?P<amount>[+-]?[0-9]+(?:\.[0-9]+)?)"
            r"(?: (?P<trailing>[A-Z]{3}))?",
            value,
        )
        if match is None or (match["leading"] and match["trailing"]):
            raise NativeClaimError("Recorded source value does not satisfy exact money typing.")
        return NativeMoney(
            amount=exact_decimal(match["amount"]),
            currency=match["leading"] or match["trailing"],
        )
    if value_type == "date":
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise NativeClaimError("Recorded source value does not satisfy exact date typing.")
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise NativeClaimError("Recorded source date is invalid.") from None
    if value_type == "boolean":
        if value not in {"true", "false"}:
            raise NativeClaimError("Recorded source value does not satisfy boolean typing.")
        return value == "true"
    return value
