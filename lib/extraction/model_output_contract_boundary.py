from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from lib.extraction.model_output_schemas import load_model_output_schema


def contract_root_payload(
    payload: dict[str, Any],
    *,
    model_output_schema_name: str | None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    if model_output_schema_name is None:
        return payload, [], []
    try:
        schema = load_model_output_schema(model_output_schema_name).schema
    except (KeyError, OSError, ValueError):
        return payload, [], []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return payload, [], []
    rejected = _off_contract_fields(payload, schema=schema, path="")
    contract_errors = _contract_validation_errors(payload, schema=schema)
    if contract_errors:
        return {}, sorted(rejected), contract_errors
    return payload, sorted(rejected), []


def merge_rejected_fields(metadata: dict[str, Any], rejected_fields: list[str]) -> None:
    if not rejected_fields:
        return
    current = metadata.get("rejected_fields")
    fields = [str(item) for item in current] if isinstance(current, list) else []
    metadata["rejected_fields"] = sorted({*fields, *rejected_fields})


def merge_contract_errors(metadata: dict[str, Any], contract_errors: list[str]) -> None:
    if not contract_errors:
        return
    current = metadata.get("model_output_contract_errors")
    errors = [str(item) for item in current] if isinstance(current, list) else []
    metadata["model_output_contract_errors"] = sorted({*errors, *contract_errors})
    repairs = [str(item) for item in metadata.get("repairs", []) if item]
    if "model_output_contract_validation_failed" not in repairs:
        repairs.append("model_output_contract_validation_failed")
    metadata["repairs"] = repairs


def _off_contract_fields(
    value: Any,
    *,
    schema: dict[str, Any],
    path: str,
) -> list[str]:
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        item_rejected: list[str] = []
        for index, item in enumerate(value):
            item_rejected.extend(
                _off_contract_fields(
                    item,
                    schema=schema["items"],
                    path=f"{path}[{index}]",
                )
            )
        return item_rejected
    if not isinstance(value, dict):
        return []
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    rejected: list[str] = []
    additional_properties = schema.get("additionalProperties")
    for key, child_value in value.items():
        child_schema = properties.get(key)
        child_path = f"{path}.{key}" if path else str(key)
        if not isinstance(child_schema, dict):
            if additional_properties is False:
                rejected.append(child_path)
            continue
        rejected.extend(
            _off_contract_fields(
                child_value,
                schema=child_schema,
                path=child_path,
            )
        )
    return rejected


def _contract_validation_errors(payload: dict[str, Any], *, schema: dict[str, Any]) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except SchemaError:
        return []
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (_path_text(tuple(error.path)), error.message),
    )
    return [f"{_path_text(tuple(error.path))}: {error.message}" for error in errors]


def _path_text(path: tuple[Any, ...]) -> str:
    if not path:
        return "$"
    rendered = "$"
    for part in path:
        if isinstance(part, int):
            rendered = f"{rendered}[{part}]"
        else:
            rendered = f"{rendered}.{part}"
    return rendered
