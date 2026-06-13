"""Expected-field vs produced-field coverage telemetry for region extractions.

Qwen's semantic plan carries ``expected_fields`` (extraction intent) on each
region task. After Granite region extraction, this module compares that intent
against the claim-bearing output of the ``RegionExtractionEnvelope`` and emits
a compact telemetry entry recorded in the extraction's ``normalization_json``:

    {"expected": [...], "produced": [...], "missing": [...], "coverage_ratio": x}

Matching rule (``MATCH_RULE``): Qwen-suggested expected names are fuzzy, so
both sides are normalized to snake case (lowercase, non-alphanumeric runs
collapse to ``_``). A produced name contributes match tokens for its full
normalized form plus, for dotted canonical keys such as
``invoice.total_amount``, the family-stripped form (``total_amount``) and the
final segment. An expected field counts as produced when a token matches
exactly, or when either side is a substring of the other and the shorter side
has at least ``_MIN_SUBSTRING_MATCH_LENGTH`` characters (so ``description``
matches ``service_description`` and ``total`` matches ``total_amount``). The
rule is deliberately recall-biased: this is telemetry only and never changes
admission or review behavior.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from lib.extraction.region_envelope import (
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
    RegionTableRow,
)

MATCH_RULE = "normalized_snake_case_exact_or_substring_min3"

_MIN_SUBSTRING_MATCH_LENGTH = 3
_MAX_PRODUCED_NAMES = 64

_LINE_ITEM_VALUE_FIELDS = (
    "description",
    "code",
    "quantity",
    "unit",
    "unit_price",
    "gross_amount",
    "allowed_amount",
    "plan_paid_amount",
    "net_amount",
    "discount_amount",
    "tax_amount",
    "currency_code",
    "service_date",
    "tax_category_hint",
    "category_hint",
)
_SOURCE_PAYLOAD_BOOKKEEPING_KEYS = {
    "confidence",
    "evidence",
    "ordinal",
    "page_number",
    "row_index",
    "source_text",
    "table_id",
}


def expected_field_coverage(
    expected_fields: Sequence[str],
    envelope: RegionExtractionEnvelope | None,
) -> dict[str, Any] | None:
    """Build the compact coverage telemetry entry, or None without expectations.

    ``produced`` is derived from the envelope's claim-bearing output (fact and
    observation names plus populated line-item/table-row field names). A
    missing envelope yields an empty ``produced`` list and zero coverage.
    """
    expected = _unique_expected(expected_fields)
    if not expected:
        return None
    produced = produced_field_names(envelope)
    produced_tokens: set[str] = set()
    for name in produced:
        produced_tokens.update(_match_tokens(name))
    missing = [
        original
        for original, normalized in expected
        if not _expected_matches(normalized, produced_tokens)
    ]
    matched = len(expected) - len(missing)
    return {
        "expected": [original for original, _ in expected],
        "produced": produced,
        "missing": missing,
        "coverage_ratio": round(matched / len(expected), 4),
        "match_rule": MATCH_RULE,
    }


def produced_field_names(envelope: RegionExtractionEnvelope | None) -> list[str]:
    """Sorted unique field names present in the envelope's claim-bearing output."""
    if envelope is None:
        return []
    names: set[str] = set()
    names.update(_fact_names(envelope.facts))
    names.update(_fact_names(envelope.observations))
    for line_item in envelope.line_items:
        names.update(_line_item_field_names(line_item))
    for table_row in envelope.table_rows:
        names.update(_table_row_field_names(table_row))
    return sorted(names)[:_MAX_PRODUCED_NAMES]


def normalized_field_name(name: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", name.lower()))


def _fact_names(facts: Iterable[RegionFact]) -> set[str]:
    return {fact.name for fact in facts if fact.name and not _is_empty(fact.value)}


def _line_item_field_names(line_item: RegionLineItem) -> set[str]:
    names = {
        field for field in _LINE_ITEM_VALUE_FIELDS if not _is_empty(getattr(line_item, field, None))
    }
    names.update(_payload_field_names(line_item.source_payload))
    return names


def _table_row_field_names(table_row: RegionTableRow) -> set[str]:
    return _payload_field_names(table_row.normalized_fields) | _payload_field_names(table_row.cells)


def _payload_field_names(payload: dict[str, Any]) -> set[str]:
    return {
        str(key)
        for key, value in payload.items()
        if str(key) not in _SOURCE_PAYLOAD_BOOKKEEPING_KEYS and not _is_empty(value)
    }


def _unique_expected(expected_fields: Sequence[str]) -> list[tuple[str, str]]:
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in expected_fields:
        original = str(raw).strip()
        normalized = normalized_field_name(original)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append((original, normalized))
    return unique


def _match_tokens(name: str) -> set[str]:
    tokens: set[str] = set()
    full = normalized_field_name(name)
    if full:
        tokens.add(full)
    segments = [segment for segment in name.split(".") if segment.strip()]
    if len(segments) > 1:
        without_family = normalized_field_name("_".join(segments[1:]))
        if without_family:
            tokens.add(without_family)
        last = normalized_field_name(segments[-1])
        if last:
            tokens.add(last)
    return tokens


def _expected_matches(expected_normalized: str, produced_tokens: set[str]) -> bool:
    for token in produced_tokens:
        if token == expected_normalized:
            return True
        shorter, longer = sorted((token, expected_normalized), key=len)
        if len(shorter) >= _MIN_SUBSTRING_MATCH_LENGTH and shorter in longer:
            return True
    return False


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}
