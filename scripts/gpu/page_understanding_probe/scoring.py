"""Exact exposed-obligation recall/grouping, never exhaustive business precision."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from lib.document_parsing.page_understanding.locators import row_key
from lib.document_parsing.page_understanding.model import PageUnderstanding


def value_identity(claim: dict[str, Any]) -> str:
    """Exact decimal arithmetic equivalence; identifiers and other text stay literal.

    Scale-only differences (12.5 / 12.50) are equal typed values, while raw source
    text preservation is independently evaluated by the structural scorer.
    """
    value = claim["typed_value"]
    kind = claim["value_type"]
    if kind == "money":
        value = {"amount": _decimal(value["amount"]), "currency": value["currency"]}
    elif kind in {"number", "quantity"}:
        value = _decimal(value)
    return json.dumps([claim["canonical_key"], kind, value], sort_keys=True, ensure_ascii=False)


def _decimal(value: str) -> str:
    parsed = Decimal(value)
    if parsed.is_zero():
        return "0"
    printed = format(parsed, "f")
    return printed.rstrip("0").rstrip(".") if "." in printed else printed


def _recall(expected: Counter[str], observed: Counter[str]) -> dict[str, Any]:
    matched = sum((expected & observed).values())
    count = sum(expected.values())
    return {
        "annotated_occurrences": count,
        "matched_occurrences": matched,
        "missing_occurrences": count - matched,
        "recall": matched / count if count else None,
        "observed_unmatched_on_annotated_keys": sum((observed - expected).values()),
        "missing": list((expected - observed).elements()),
    }


def score_page(page: PageUnderstanding, expected: dict[str, Any]) -> dict[str, Any]:
    if page.page_number != expected["page_number"]:
        raise ValueError("Observed page differs from the authored expectation identity.")
    fields = expected["fields"]
    rows = expected["rows"]
    scalar_keys = {item["canonical_key"] for item in fields}
    line_keys = {item["canonical_key"] for row in rows for item in row["claims"]}
    scalar, line = [], []
    grouped: dict[tuple[str, int, int | None], list[str]] = defaultdict(list)
    unscored = []
    for claim in page.extraction.claims:
        value = claim.model_dump(mode="json")
        if claim.physical_row is None and claim.canonical_key in scalar_keys:
            scalar.append(value_identity(value))
        elif claim.physical_row is not None and claim.canonical_key in line_keys:
            identity = value_identity(value)
            line.append(identity)
            grouped[row_key(claim.physical_row)].append(identity)
        else:
            unscored.append(value)
    expected_lines = Counter(value_identity(c) for row in rows for c in row["claims"])
    expected_rows = Counter(
        _row_signature(value_identity(c) for c in row["claims"]) for row in rows
    )
    observed_rows = Counter(_row_signature(values) for values in grouped.values())
    ledger = next(
        (item for item in page.extraction.families if item.family == expected["family"]), None
    )
    field_states = {item.canonical_key: item.state for item in ledger.fields} if ledger else {}
    present = sum(field_states.get(key) == "present" for key in scalar_keys)
    return {
        "page_number": page.page_number,
        "classification": {
            "expected_family": expected["family"],
            "exact_primary_family": page.classification.outcome == "known"
            and page.classification.primary_family == expected["family"],
            "observed": page.classification.model_dump(mode="json"),
        },
        "annotated_scalar_values": _recall(Counter(map(value_identity, fields)), Counter(scalar)),
        "annotated_line_values": _recall(expected_lines, Counter(line)),
        "physical_row_grouping": {
            **_recall(expected_rows, observed_rows),
            "expected_printed_rows": len(rows),
            "observed_rows_with_annotated_keys": len(grouped),
            "scope": "complete annotated value multisets grouped by model structural row identity",
            "pixel_row_grounding": "not_evaluated",
        },
        "model_reported_ledger": {
            "disposition": page.extraction.disposition,
            "annotated_scalar_obligations": len(scalar_keys),
            "annotated_scalar_keys_reported_present": present,
            "annotated_scalar_states": {
                key: field_states.get(key, "missing_ledger") for key in sorted(scalar_keys)
            },
            "row_inventory": ledger.row_inventory if ledger else None,
            "recorded_rows": len(ledger.rows) if ledger else 0,
            "excluded_rows": len(ledger.excluded_rows) if ledger else 0,
            "note": "Absence ledgers are model observations, not source-authored absence truth.",
        },
        "unscored_extra_claims": unscored,
        "unscored_extra_claim_count": len(unscored),
        "overall_precision": "not_evaluated",
        "full_business_coverage": "not_evaluated",
    }


def _row_signature(values: Any) -> str:
    return json.dumps(sorted(values), ensure_ascii=False)
