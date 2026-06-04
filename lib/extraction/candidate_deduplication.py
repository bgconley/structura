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
        line_item_sparse_key(fact) for fact in unique if line_item_has_meaningful_detail(fact)
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
    )


def line_item_sparse_key(fact: LineItemCandidateFact) -> tuple[Any, ...]:
    return (
        normalized_text_key(fact.line_item_type),
        normalized_text_key(fact.description),
        normalized_text_key(fact.code),
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
        normalized_text_key(candidate.field_name),
        normalized_text_key(candidate.value_type),
        json_key(candidate.value),
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
