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
        return {"amount": float(value["amount"]), "currency": value.get("currency") or "USD"}
    amount = number_value(value)
    if amount is None:
        return None
    return {"amount": amount, "currency": "USD"}


def number_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
        if match:
            return float(match.group(0).replace(",", ""))
    return None


def string_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
