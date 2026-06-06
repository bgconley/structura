from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from typing import Any

from lib.extraction.candidate_value_parsing import date_key, float_key, normalized_text_key
from lib.extraction.models import LineItemCandidateFact, ObservationCandidateFact


def dedupe_line_item_candidates(
    facts: list[LineItemCandidateFact],
) -> list[LineItemCandidateFact]:
    exact: dict[tuple[Any, ...], LineItemCandidateFact] = {}
    for fact in facts:
        key = line_item_exact_key(fact)
        current = exact.get(key)
        if current is None or line_item_richness(fact) > line_item_richness(current):
            exact[key] = fact

    unique = list(exact.values())
    rich_sparse_keys = {
        key
        for fact in unique
        if line_item_has_meaningful_detail(fact)
        for key in line_item_sparse_keys_for_rich_fact(fact)
    }
    filtered = [
        fact
        for fact in unique
        if not (line_item_is_sparse(fact) and line_item_sparse_key(fact) in rich_sparse_keys)
    ]
    return [replace(fact, ordinal=index + 1) for index, fact in enumerate(filtered)]


def line_item_exact_key(fact: LineItemCandidateFact) -> tuple[Any, ...]:
    return (
        normalized_text_key(fact.line_item_type),
        normalized_text_key(fact.description),
        normalized_text_key(fact.code),
        date_key(fact.service_date),
        float_key(fact.quantity),
        normalized_text_key(fact.unit),
        float_key(fact.unit_price),
        float_key(fact.gross_amount),
        float_key(fact.discount_amount),
        float_key(fact.tax_amount),
        float_key(fact.net_amount),
        normalized_text_key(fact.currency),
        evidence_locator_key(fact.evidence),
    )


def line_item_sparse_key(fact: LineItemCandidateFact) -> tuple[Any, ...]:
    return _line_item_sparse_key(fact, evidence_locator_key(fact.evidence))


def line_item_sparse_keys_for_rich_fact(fact: LineItemCandidateFact) -> tuple[tuple[Any, ...], ...]:
    located_key = line_item_sparse_key(fact)
    evidence_less_key = _line_item_sparse_key(fact, ())
    if located_key == evidence_less_key:
        return (located_key,)
    return (located_key, evidence_less_key)


def _line_item_sparse_key(
    fact: LineItemCandidateFact,
    locator_key: tuple[Any, ...],
) -> tuple[Any, ...]:
    return (
        normalized_text_key(fact.line_item_type),
        normalized_text_key(fact.description),
        normalized_text_key(fact.code),
        locator_key,
    )


def line_item_is_sparse(fact: LineItemCandidateFact) -> bool:
    return not line_item_has_meaningful_detail(fact)


def line_item_has_meaningful_detail(fact: LineItemCandidateFact) -> bool:
    return any(
        value is not None
        for value in (
            fact.code,
            fact.service_date,
            fact.quantity,
            fact.unit_price,
            fact.gross_amount,
            fact.discount_amount,
            fact.tax_amount,
            fact.net_amount,
        )
    )


def line_item_richness(fact: LineItemCandidateFact) -> int:
    populated = (
        fact.code,
        fact.service_date,
        fact.quantity,
        fact.unit,
        fact.unit_price,
        fact.gross_amount,
        fact.discount_amount,
        fact.tax_amount,
        fact.net_amount,
        fact.currency,
        fact.category_hint,
    )
    return sum(value not in (None, "") for value in populated) + len(fact.evidence)


def dedupe_observation_candidates(
    candidates: list[ObservationCandidateFact],
) -> list[ObservationCandidateFact]:
    deduped: dict[tuple[Any, ...], ObservationCandidateFact] = {}
    for candidate in candidates:
        key = observation_key(candidate)
        if key not in deduped:
            deduped[key] = candidate
    return list(deduped.values())


def observation_key(candidate: ObservationCandidateFact) -> tuple[Any, ...]:
    return (
        normalized_text_key(candidate.observation_family),
        normalized_text_key(candidate.metadata.get("semantic_type")),
        normalized_text_key(candidate.field_name),
        normalized_text_key(candidate.value_type),
        json_key(candidate.value),
        evidence_locator_key(candidate.evidence),
    )


def evidence_locator_key(evidence: list[dict[str, Any]]) -> tuple[Any, ...]:
    selected = _selected_evidence(evidence)
    if not _has_deduplication_locator(selected):
        return ()
    return (
        normalized_text_key(selected.get("semantic_region_id")),
        selected.get("page_number"),
        normalized_text_key(selected.get("page_id")),
        normalized_text_key(selected.get("element_id")),
        normalized_text_key(selected.get("table_id")),
        selected.get("row_index"),
        json_key(selected.get("bbox")) if selected.get("bbox") is not None else "",
    )


def _selected_evidence(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    refs = [ref for ref in evidence if isinstance(ref, dict)]
    if not refs:
        return {}
    return min(refs, key=_evidence_selection_key)


def _evidence_selection_key(evidence: dict[str, Any]) -> tuple[int, int, str, str, int, str]:
    return (
        -_evidence_specificity(evidence),
        _int_key(evidence.get("page_number")),
        normalized_text_key(evidence.get("semantic_region_id")),
        normalized_text_key(evidence.get("page_id")),
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
            evidence.get("page_number") is not None or evidence.get("page_id") not in (None, ""),
            evidence.get("semantic_region_id") not in (None, ""),
        )
    )


def _int_key(value: Any) -> int:
    if isinstance(value, int):
        return value
    return 1_000_000_000


def _stable_locator_json(evidence: dict[str, Any]) -> str:
    return json.dumps(
        {
            "bbox": json_key_value(evidence.get("bbox")),
            "element_id": normalized_text_key(evidence.get("element_id")),
            "table_id": normalized_text_key(evidence.get("table_id")),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _has_deduplication_locator(evidence: dict[str, Any]) -> bool:
    return any(
        evidence.get(key) not in (None, "", [])
        for key in ("semantic_region_id", "table_id", "element_id", "bbox")
    )


def json_key(value: Any) -> str:
    return json.dumps(json_key_value(value), sort_keys=True, separators=(",", ":"))


def json_key_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalized_text_key(value)
    if isinstance(value, dict):
        return {str(key): json_key_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_key_value(item) for item in value]
    if isinstance(value, date):
        return value.isoformat()
    return value
