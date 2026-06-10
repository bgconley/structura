from __future__ import annotations

import re
from typing import Any


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, dict | list):
        return "json"
    return "string"


def bounded_text(value: object, *, max_length: int) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= max_length:
        return text
    return text[:max_length]


def money_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("amount") is not None:
        amount = number_value(value["amount"])
        if amount is None:
            return None
        payload: dict[str, Any] = {"amount": amount}
        currency = value.get("currency") or value.get("currency_code")
        if currency not in (None, ""):
            payload["currency"] = str(currency).upper()
        return payload
    amount = number_value(value)
    if amount is None:
        return None
    return {"amount": amount}


def number_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return parse_decimal_text(value)
    return None


def parse_decimal_text(value: str) -> float | None:
    """Parse a human-formatted amount string deterministically.

    Handles accounting negatives ("(125.00)", "125.00-", "-$125.00"),
    US thousands/decimal ("1,234.56"), and European thousands/decimal
    ("1.234,56", "12,34"). Ambiguous single separators keep the historical
    US bias: a comma followed by exactly three digits is a thousands mark.
    """
    text = value.strip()
    if not text:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    if text.endswith("-"):
        negative = True
        text = text[:-1].strip()
    match = re.search(r"\d(?:[\d.,]*\d)?", text)
    if match is None:
        return None
    if "-" in text[: match.start()]:
        negative = True
    amount = _parse_decimal_token(match.group(0))
    if amount is None:
        return None
    return -amount if negative else amount


def _parse_decimal_token(token: str) -> float | None:
    has_comma = "," in token
    has_dot = "." in token
    if has_comma and has_dot:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif has_comma:
        head, _, tail = token.rpartition(",")
        if "," in head or (len(tail) == 3 and head):
            token = token.replace(",", "")
        else:
            token = f"{head}.{tail}"
    elif has_dot and token.count(".") > 1:
        token = token.replace(".", "")
    try:
        return float(token)
    except ValueError:
        return None


def string_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
