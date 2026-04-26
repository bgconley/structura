from __future__ import annotations

import json
import re
from typing import Any

SUPPORTED_CONDITION_FIELDS = {
    "document_family",
    "document_subtype",
    "counterparty",
    "contacts",
    "tags",
    "folders",
    "folder_paths",
    "folder_ids",
    "document_date",
    "amount_total",
    "review_status",
    "sensitivity",
    "search_text",
}
SUPPORTED_OPERATORS = {"eq", "neq", "contains", "in", "gte", "lte", "exists", "regex"}
SUPPORTED_ACTION_TYPES = {
    "add_folder",
    "set_primary_folder",
    "add_tag",
    "set_sensitivity",
    "create_review_task",
    "set_document_type",
}
SUPPORTED_SENSITIVITY = {"normal", "pii", "financial", "medical", "legal", "highly_sensitive"}

_NESTED_QUANTIFIER_RE = re.compile(r"\([^)]*[*+][^)]*\)\s*[*+{]")


class RuleValidationError(ValueError):
    pass


def validate_rule_definition(payload: dict[str, Any]) -> dict[str, Any]:
    name = _normalized_text(payload.get("name"), "Rule name")
    conditions = _list(payload.get("conditions"), "conditions")
    actions = _list(payload.get("actions"), "actions")
    if not conditions:
        raise RuleValidationError("Filing rules require at least one condition.")
    if not actions:
        raise RuleValidationError("Filing rules require at least one action.")
    normalized_conditions = [_validate_condition(condition) for condition in conditions]
    normalized_actions = [_validate_action(action) for action in actions]
    priority = int(payload.get("priority", 50))
    if priority < 0 or priority > 100:
        raise RuleValidationError("priority must be between 0 and 100.")
    return {
        "id": payload.get("id"),
        "name": name,
        "description": _optional_text(payload.get("description")),
        "enabled": bool(payload.get("enabled", True)),
        "priority": priority,
        "review_required": bool(
            payload.get("review_required", payload.get("reviewRequired", True))
        ),
        "conditions": normalized_conditions,
        "actions": normalized_actions,
    }


def validate_policy_json_serializable(value: dict[str, Any], *, max_bytes: int = 8192) -> None:
    try:
        encoded = json.dumps(value, sort_keys=True)
    except TypeError as exc:
        raise RuleValidationError("JSON payload is not serializable.") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise RuleValidationError("JSON payload is too large.")


def _validate_condition(condition: object) -> dict[str, Any]:
    if not isinstance(condition, dict):
        raise RuleValidationError("Each condition must be an object.")
    field = _normalized_text(condition.get("field"), "Condition field")
    if field not in SUPPORTED_CONDITION_FIELDS and not field.startswith("canonical."):
        raise RuleValidationError(f"Unsupported condition field: {field}")
    op = _normalized_text(condition.get("op"), "Condition operator")
    if op not in SUPPORTED_OPERATORS:
        raise RuleValidationError(f"Unsupported condition operator: {op}")
    if op != "exists" and "value" not in condition:
        raise RuleValidationError("Condition value is required unless op is exists.")
    value = condition.get("value")
    if op == "regex":
        if not isinstance(value, str) or not value:
            raise RuleValidationError("regex conditions require a non-empty string value.")
        if len(value) > 128 or _NESTED_QUANTIFIER_RE.search(value):
            raise RuleValidationError("regex condition is too complex for safe evaluation.")
        try:
            re.compile(value)
        except re.error as exc:
            raise RuleValidationError(f"Invalid regex condition: {exc}") from exc
    return {"field": field, "op": op, "value": value}


def _validate_action(action: object) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise RuleValidationError("Each action must be an object.")
    action_type = _normalized_text(action.get("type"), "Action type")
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise RuleValidationError(f"Unsupported action type: {action_type}")
    normalized = dict(action)
    normalized["type"] = action_type
    if action_type in {"add_folder", "set_primary_folder"}:
        if not normalized.get("folder_id") and not normalized.get("folder_path"):
            raise RuleValidationError(f"{action_type} requires folder_id or folder_path.")
    if action_type == "add_tag":
        tag = _normalized_text(normalized.get("tag"), "Action tag")
        normalized["tag"] = tag
    if action_type == "set_sensitivity":
        value = _normalized_text(normalized.get("value"), "Sensitivity value")
        if value not in SUPPORTED_SENSITIVITY:
            raise RuleValidationError(f"Unsupported sensitivity: {value}")
        normalized["value"] = value
    if action_type == "create_review_task":
        normalized["value"] = _optional_text(normalized.get("value")) or "Review suggested filing."
    if action_type == "set_document_type":
        normalized["value"] = _normalized_text(normalized.get("value"), "Document type")
    return normalized


def _normalized_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise RuleValidationError(f"{label} is required.")
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise RuleValidationError(f"{label} is required.")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuleValidationError("Optional text values must be strings.")
    normalized = value.strip()
    return normalized or None


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise RuleValidationError(f"{label} must be an array.")
    return value
