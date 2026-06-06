from __future__ import annotations

from typing import Any

from lib.extraction.model_output_schemas import load_model_output_schema


def contract_root_payload(
    payload: dict[str, Any],
    *,
    model_output_schema_name: str | None,
) -> tuple[dict[str, Any], list[str]]:
    if model_output_schema_name is None:
        return payload, []
    try:
        schema = load_model_output_schema(model_output_schema_name).schema
    except (KeyError, OSError, ValueError):
        return payload, []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return payload, []
    allowed = {str(key) for key in properties}
    rejected = sorted(str(key) for key in payload if key not in allowed)
    if not rejected:
        return payload, []
    return {key: value for key, value in payload.items() if key in allowed}, rejected


def merge_rejected_fields(metadata: dict[str, Any], rejected_fields: list[str]) -> None:
    if not rejected_fields:
        return
    current = metadata.get("rejected_fields")
    fields = [str(item) for item in current] if isinstance(current, list) else []
    metadata["rejected_fields"] = sorted({*fields, *rejected_fields})
