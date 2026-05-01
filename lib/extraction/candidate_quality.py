from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

PROMPT_ECHO_PATTERNS = (
    "identify and extract",
    "extract the schema",
    "extruct the schema",
    "tabls schema",
    "table schema",
    "tables in the image",
    "reading order",
    "return only json",
    "matching the schema",
)

PLACEHOLDER_FIELD_NAMES = {
    "visible_field",
    "field",
    "key",
    "value",
}

PLACEHOLDER_VALUES = {
    "",
    "null",
    "none",
    "n/a",
    "unknown",
    "missing",
    "not found",
    "visible value",
    "example value",
}


def contains_prompt_echo(value: object) -> bool:
    text = str(value or "").lower()
    return any(pattern in text for pattern in PROMPT_ECHO_PATTERNS)


def reject_observation(field_name: str, value: object) -> tuple[bool, str | None]:
    name = str(field_name or "").strip().lower()
    val = str(value or "").strip().lower()

    if name in PLACEHOLDER_FIELD_NAMES:
        return True, "placeholder_field_name"
    if val in PLACEHOLDER_VALUES:
        return True, "placeholder_or_null_value"
    if contains_prompt_echo(name) or contains_prompt_echo(val):
        return True, "prompt_or_schema_echo"
    return False, None


def reject_scalar_candidate(value: object) -> tuple[bool, str | None]:
    if contains_prompt_echo(value):
        return True, "prompt_or_schema_echo"
    if isinstance(value, str) and value.strip().lower() in PLACEHOLDER_VALUES:
        return True, "placeholder_or_null_value"
    return False, None


def reject_line_item(item: dict[str, Any]) -> tuple[bool, str | None]:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("description", "service_description", "category_hint", "unit", "code")
    ).lower()

    if contains_prompt_echo(text):
        return True, "prompt_or_schema_echo"

    numeric_one_count = sum(
        _numeric_value_is_one(item.get(key))
        for key in ("quantity", "unit_price", "gross_amount", "net_amount", "amount")
    )
    if numeric_one_count >= 2 and ("schema" in text or "rows" in text):
        return True, "fake_schema_line_item"

    description = str(item.get("description") or item.get("service_description") or "").strip()
    if not description:
        return True, "missing_description"

    if description.lower() in PLACEHOLDER_VALUES:
        return True, "placeholder_or_null_value"

    return False, None


def _numeric_value_is_one(value: object) -> bool:
    if isinstance(value, dict):
        value = value.get("amount")
    if isinstance(value, int | float | Decimal):
        return _decimal_value_is_one(str(value))
    if isinstance(value, str):
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
        if match:
            return _decimal_value_is_one(match.group(0).replace(",", ""))
    return False


def _decimal_value_is_one(value: str) -> bool:
    try:
        return Decimal(value) == Decimal("1")
    except (InvalidOperation, ValueError):
        return False
