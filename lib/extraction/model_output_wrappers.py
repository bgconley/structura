from __future__ import annotations

from typing import Any


def unwrap_model_output_payload(payload: Any) -> tuple[dict[str, Any], list[str]]:
    repairs: list[str] = []
    if not isinstance(payload, dict):
        repairs.append(f"dropped_non_object_{type(payload).__name__}_model_output_payload")
        return {}, repairs
    normalized = payload.get("normalized")
    if isinstance(normalized, dict):
        repairs.append("unwrapped_normalized_payload")
        return _merged_wrapper_payload(payload, normalized, wrapper_key="normalized"), repairs
    data = payload.get("data")
    if isinstance(data, dict):
        repairs.append("unwrapped_data_payload")
        return _merged_wrapper_payload(payload, data, wrapper_key="data"), repairs
    return payload, repairs


def _merged_wrapper_payload(
    payload: dict[str, Any],
    wrapped: dict[str, Any],
    *,
    wrapper_key: str,
) -> dict[str, Any]:
    merged = {key: value for key, value in payload.items() if key != wrapper_key}
    merged.update(wrapped)
    return merged
