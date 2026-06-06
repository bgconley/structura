from __future__ import annotations

from typing import Any


def unwrap_model_output_payload(payload: Any) -> tuple[dict[str, Any], list[str]]:
    repairs: list[str] = []
    if not isinstance(payload, dict):
        repairs.append(f"dropped_non_object_{type(payload).__name__}_model_output_payload")
        return {}, repairs
    return payload, repairs
