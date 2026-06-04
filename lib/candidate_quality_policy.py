from __future__ import annotations

import re
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
SCHEMA_ARTIFACT_KEYS = frozenset(
    {
        "$schema",
        "json_schema",
        "response_format",
        "system_prompt",
        "tool_schema",
    }
)
SCHEMA_ARTIFACT_VALUES = (
    "$schema",
    "json schema",
    "response_format",
    "tool schema",
)
SCHEMA_ARTIFACT_VALUE_TOKENS = frozenset(
    {
        "$schema",
        "json_schema",
        "response_format",
        "system_prompt",
        "tool_schema",
    }
)


def contains_prompt_echo(value: object) -> bool:
    text = str(value or "").lower()
    token = _normalized_key(value)
    return any(pattern in text for pattern in PROMPT_ECHO_PATTERNS) or any(
        _normalized_key(pattern) in token for pattern in PROMPT_ECHO_PATTERNS
    )


def contains_prompt_or_schema_artifact(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_schema_artifact_key(key) or contains_prompt_echo(key):
                return True
            if contains_prompt_or_schema_artifact(item):
                return True
        return False
    if isinstance(value, list | tuple | set):
        return any(contains_prompt_or_schema_artifact(item) for item in value)
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    normalized_token = _normalized_key(value)
    if normalized in {"<json_schema>", "json_schema", "response_format"}:
        return True
    if normalized_token in SCHEMA_ARTIFACT_VALUE_TOKENS:
        return True
    if contains_prompt_echo(value):
        return True
    return any(token in normalized for token in SCHEMA_ARTIFACT_VALUES) or any(
        token in normalized_token for token in SCHEMA_ARTIFACT_VALUE_TOKENS
    )


def _is_schema_artifact_key(value: object) -> bool:
    normalized = _normalized_key(value)
    return normalized in SCHEMA_ARTIFACT_KEYS


def _normalized_key(value: object) -> str:
    text = str(value or "").strip().replace("-", "_").replace(" ", "_")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    return "_".join(part for part in text.lower().split("_") if part)
