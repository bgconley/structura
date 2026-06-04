from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


def all_rows(documents: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for doc in documents:
        value = get_value(doc, key)
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    return rows


def get_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def int_value(value: Any, *, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def sum_values(rows: list[dict[str, Any]], *keys: str) -> int:
    return sum(int_value(get_value(row, *keys)) for row in rows)


def first_value(rows: list[dict[str, Any]], *keys: str) -> str | None:
    for row in rows:
        value = get_value(row, *keys)
        if value not in (None, ""):
            return str(value)
    return None


def first_report_value(rows: list[dict[str, Any]], key: str) -> Any:
    for row in rows:
        report = dict_value(get_value(row, "report_json", "reportJson"))
        value = get_value(report, key, snake(key))
        if value is not None:
            return value
    return None


def select_values(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {
        key: get_value(row, key, camel(key))
        for key in keys
        if get_value(row, key, camel(key)) is not None
    }


def fingerprint(payload: Any) -> str:
    encoded = json.dumps(json_safe(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(json_safe(key)): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [json_safe(item) for item in value]
    return str(value)


def camel(key: str) -> str:
    head, *tail = key.split("_")
    return head + "".join(part.capitalize() for part in tail)


def snake(key: str) -> str:
    chars: list[str] = []
    for char in key:
        if char.isupper():
            chars.append("_")
            chars.append(char.lower())
        else:
            chars.append(char)
    return "".join(chars).lstrip("_")


def normalized_decision(value: Any) -> str:
    return normalized_token(value)


def normalized_token(value: Any) -> str:
    token = snake(str(value or "").strip()).lower().replace("-", "_").replace(" ", "_")
    return "_".join(part for part in token.split("_") if part)


def normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()
