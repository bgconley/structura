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
    shaped, rejected = _shape_object(payload, schema=schema, path="")
    return shaped, sorted(rejected)


def merge_rejected_fields(metadata: dict[str, Any], rejected_fields: list[str]) -> None:
    if not rejected_fields:
        return
    current = metadata.get("rejected_fields")
    fields = [str(item) for item in current] if isinstance(current, list) else []
    metadata["rejected_fields"] = sorted({*fields, *rejected_fields})


def _shape_value(value: Any, *, schema: dict[str, Any], path: str) -> tuple[Any, list[str]]:
    if isinstance(value, dict) and isinstance(schema.get("properties"), dict):
        return _shape_object(value, schema=schema, path=path)
    items_schema = schema.get("items")
    if isinstance(value, list) and isinstance(items_schema, dict):
        shaped_items: list[Any] = []
        rejected: list[str] = []
        for index, item in enumerate(value):
            shaped_item, item_rejected = _shape_value(
                item,
                schema=items_schema,
                path=f"{path}[{index}]",
            )
            rejected.extend(item_rejected)
            if item_rejected and isinstance(item, dict):
                continue
            shaped_items.append(shaped_item)
        return shaped_items, rejected
    return value, []


def _shape_object(
    payload: dict[str, Any],
    *,
    schema: dict[str, Any],
    path: str,
) -> tuple[dict[str, Any], list[str]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return payload, []
    shaped: dict[str, Any] = {}
    rejected: list[str] = []
    for key, value in payload.items():
        child_schema = properties.get(key)
        child_path = f"{path}.{key}" if path else str(key)
        if not isinstance(child_schema, dict):
            rejected.append(child_path)
            continue
        shaped_value, child_rejected = _shape_value(
            value,
            schema=child_schema,
            path=child_path,
        )
        shaped[str(key)] = shaped_value
        rejected.extend(child_rejected)
    return shaped, rejected
