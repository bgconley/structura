from __future__ import annotations


def decision_for_quality_reason(reason: str | None) -> tuple[str, tuple[str, ...]]:
    normalized = reason or "candidate_quality_gate"
    if normalized in {"prompt_or_schema_echo", "fake_schema_line_item"}:
        return "rejected_artifact", (normalized,)
    if "placeholder" in normalized or "null" in normalized or normalized == "missing_description":
        return "rejected_placeholder", (normalized,)
    return "rejected_value_sanity", (normalized,)
