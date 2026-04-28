from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_SENSITIVE_KEY_FRAGMENTS = (
    "answer",
    "data_url",
    "image_path",
    "object_uri",
    "objecturi",
    "path",
    "prompt",
    "raw_output",
    "raw_text",
    "response",
    "text",
    "uri",
    "url",
)


def redact_model_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: (
                "[redacted]" if _is_sensitive_key(str(key)) else redact_model_payload(nested_value)
            )
            for key, nested_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [redact_model_payload(item) for item in value]
    if isinstance(value, str) and _looks_like_sensitive_value(value):
        return "[redacted]"
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.replace("-", "_").casefold()
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _looks_like_sensitive_value(value: str) -> bool:
    return value.startswith(("data:", "filesystem://", "/srv/structura/"))
