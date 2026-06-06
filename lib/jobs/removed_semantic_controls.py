from __future__ import annotations

from collections.abc import Mapping

REMOVED_SEMANTIC_CONTROL_MESSAGE = "Removed high-quality/rescue semantic controls are not accepted."


def has_removed_semantic_controls(payload: Mapping[str, object]) -> bool:
    return (
        _non_smart_mode(payload.get("quality_mode"))
        or _non_smart_mode(payload.get("semantic_quality_mode"))
        or _truthy_control(payload.get("allow_8b_rescue"))
        or _truthy_control(payload.get("semantic_rescue"))
        or _truthy_control(payload.get("rescue_failure_class"))
    )


def _non_smart_mode(value: object) -> bool:
    if value in (None, ""):
        return False
    return str(value).strip().lower() != "smart"


def _truthy_control(value: object) -> bool:
    if value in (None, "", False):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
