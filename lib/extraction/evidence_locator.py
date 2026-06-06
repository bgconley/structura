from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def selected_evidence_ref(evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    refs = [dict(ref) for ref in evidence if isinstance(ref, Mapping)]
    if not refs:
        return {}
    return min(refs, key=_evidence_selection_key)


def _evidence_selection_key(evidence: dict[str, Any]) -> tuple[int, int, int, str, str, int, str]:
    return (
        -_evidence_specificity(evidence),
        _locator_rank(evidence),
        _int_key(evidence.get("page_number")),
        _normalized_text(evidence.get("semantic_region_id")),
        _normalized_text(evidence.get("page_id")),
        _int_key(evidence.get("row_index")),
        _stable_locator_json(evidence),
    )


def _evidence_specificity(evidence: dict[str, Any]) -> int:
    return sum(
        (
            evidence.get("row_index") is not None,
            evidence.get("table_id") not in (None, ""),
            evidence.get("element_id") not in (None, ""),
            evidence.get("bbox") is not None,
            evidence.get("text_span") is not None,
            evidence.get("page_number") is not None or evidence.get("page_id") not in (None, ""),
            evidence.get("semantic_region_id") not in (None, ""),
        )
    )


def _locator_rank(evidence: dict[str, Any]) -> int:
    return {
        "table_row": 0,
        "table": 1,
        "element": 2,
        "page": 3,
        "semantic_region": 4,
        "unknown": 5,
    }[_locator_kind(evidence)]


def _locator_kind(evidence: dict[str, Any]) -> str:
    if evidence.get("row_index") is not None:
        return "table_row"
    if evidence.get("table_id") not in (None, ""):
        return "table"
    if evidence.get("element_id") not in (None, ""):
        return "element"
    if evidence.get("page_number") is not None or evidence.get("page_id") not in (None, ""):
        return "page"
    if evidence.get("semantic_region_id") not in (None, ""):
        return "semantic_region"
    return "unknown"


def _int_key(value: Any) -> int:
    if isinstance(value, int):
        return value
    return 1_000_000_000


def _stable_locator_json(evidence: dict[str, Any]) -> str:
    return json.dumps(
        {
            "bbox": _json_key_value(evidence.get("bbox")),
            "element_id": _normalized_text(evidence.get("element_id")),
            "table_id": _normalized_text(evidence.get("table_id")),
            "text_span": _json_key_value(evidence.get("text_span")),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalized_text(value: object) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).strip().lower().split())


def _json_key_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalized_text(value)
    if isinstance(value, dict):
        return {str(key): _json_key_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_key_value(item) for item in value]
    return value
