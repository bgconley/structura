from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from lib.candidate_quality_policy import contains_prompt_or_schema_artifact

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
PRIMARY_VALUE_KEYS = {
    "amount",
    "date",
    "description",
    "display_name",
    "field_name",
    "field_value",
    "key",
    "merchant",
    "name",
    "seller",
    "text",
    "total",
    "value",
}


def reject_observation(field_name: str, value: object) -> tuple[bool, str | None]:
    name = str(field_name or "").strip().lower()
    val = "" if value is None else str(value).strip().lower()

    if not name or name in PLACEHOLDER_FIELD_NAMES:
        return True, "placeholder_field_name"
    if val in PLACEHOLDER_VALUES:
        return True, "placeholder_or_null_value"
    if contains_prompt_or_schema_artifact(name) or contains_prompt_or_schema_artifact(val):
        return True, "prompt_or_schema_echo"
    return False, None


def reject_scalar_candidate(value: object) -> tuple[bool, str | None]:
    if contains_prompt_or_schema_artifact(value):
        return True, "prompt_or_schema_echo"
    if _contains_placeholder_value(value):
        return True, "placeholder_or_null_value"
    return False, None


def reject_line_item(item: dict[str, Any]) -> tuple[bool, str | None]:
    if contains_prompt_or_schema_artifact(item):
        return True, "prompt_or_schema_echo"

    text = " ".join(
        str(item.get(key) or "")
        for key in ("description", "service_description", "category_hint", "unit", "code")
    ).lower()

    if contains_prompt_or_schema_artifact(text):
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

    zero_rejected, zero_reason = zero_amount_line_requires_context(item)
    if zero_rejected:
        return True, zero_reason

    return False, None


def zero_amount_line_requires_context(item: dict[str, Any]) -> tuple[bool, str | None]:
    amounts = (
        item.get("gross_amount"),
        item.get("net_amount"),
        item.get("unit_price"),
        item.get("amount"),
        item.get("billed_amount"),
        item.get("allowed_amount"),
        item.get("paid_amount"),
        item.get("patient_responsibility"),
    )
    all_zero_or_missing = all(_amount_is_zero_or_missing(value) for value in amounts)
    if not all_zero_or_missing:
        return False, None

    description = str(item.get("description") or item.get("service_description") or "").strip()
    code = str(item.get("code") or item.get("procedure_code") or "").strip()
    service_date = str(item.get("service_date") or "").strip()
    category_hint = str(item.get("category_hint") or "").strip()

    if len(description) >= 12 and (
        code or service_date or category_hint or "service" in description.lower()
    ):
        return False, None

    return True, "zero_amount_without_service_context"


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


def _amount_is_zero_or_missing(value: object) -> bool:
    if value in (None, ""):
        return True
    if isinstance(value, dict):
        value = value.get("amount")
    if isinstance(value, int | float | Decimal):
        return _decimal_value_is_zero(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", stripped)
        if match:
            return _decimal_value_is_zero(match.group(0).replace(",", ""))
    return False


def _decimal_value_is_one(value: str) -> bool:
    try:
        return Decimal(value) == Decimal("1")
    except (InvalidOperation, ValueError):
        return False


def _decimal_value_is_zero(value: str) -> bool:
    try:
        return Decimal(value) == Decimal("0")
    except (InvalidOperation, ValueError):
        return False


def _contains_placeholder_value(value: object, *, key: object | None = None) -> bool:
    if value is None:
        return key is None or _normalized_key(key) in PRIMARY_VALUE_KEYS
    if isinstance(value, str):
        return (
            key is None or _normalized_key(key) in PRIMARY_VALUE_KEYS
        ) and value.strip().lower() in PLACEHOLDER_VALUES
    if isinstance(value, dict):
        return any(
            _contains_placeholder_value(item, key=item_key) for item_key, item in value.items()
        )
    if isinstance(value, list | tuple | set):
        return any(_contains_placeholder_value(item, key=key) for item in value)
    return False


def _normalized_key(value: object) -> str:
    return str(value or "").strip().replace("-", "_").replace(" ", "_").lower()
