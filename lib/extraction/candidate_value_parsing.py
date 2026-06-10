from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.model_output_value_parsing import parse_decimal_text
from lib.extraction.models import Evidence, ValidationReport


def candidate_status(
    validation: ValidationReport,
    evidence: list[dict[str, Any]],
    *,
    source_engine: str,
) -> str:
    if (
        validation.needs_review
        or source_engine.startswith("qwen3_vl")
        or not has_concrete_evidence(evidence)
    ):
        return "needs_review"
    return "proposed"


def first_evidence(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        return evidence
    for value in payload.values():
        if isinstance(value, dict):
            evidence = value.get("evidence")
            if isinstance(evidence, list):
                return evidence
    return []


def evidence(owner: dict[str, Any]) -> list[Evidence]:
    evidence_value = owner.get("evidence")
    return evidence_value if isinstance(evidence_value, list) else []


def overall_confidence(payload: dict[str, Any]) -> float:
    confidence = payload.get("confidence")
    if isinstance(confidence, dict):
        return float(confidence.get("overall") or 0)
    return 0.0


def money_amount(value: Any) -> float | None:
    if not isinstance(value, dict) or value.get("amount") is None:
        return None
    return float(value["amount"])


def money_currency(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    currency = value.get("currency")
    return str(currency) if currency else None


def number_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return parse_decimal_text(value)
    return None


def number_or_none(value: Any) -> float | None:
    try:
        return number_value(value)
    except (TypeError, ValueError):
        return None


def confidence_or_none(value: Any) -> float | None:
    confidence = number_or_none(value)
    if confidence is None or not 0.0 <= confidence <= 1.0:
        return None
    return confidence


def empty_observation_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def grid_only_observation(field_name: Any, value: Any) -> bool:
    field = normalized_text_key(field_name)
    if field == "dimensions":
        return True
    if field != "cells":
        return False
    return not contains_textual_content(value)


def contains_textual_content(value: Any) -> bool:
    if isinstance(value, str):
        return any(char.isalpha() for char in value)
    if isinstance(value, dict):
        return any(contains_textual_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(contains_textual_content(item) for item in value)
    return False


def normalized_text_key(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def float_key(value: float | None) -> float | None:
    return round(float(value), 6) if value is not None else None


def date_key(value: date | None) -> str:
    return value.isoformat() if isinstance(value, date) else ""


def date_value(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    candidates = [
        text,
        *date_fragments(text),
    ]
    for candidate in dict.fromkeys(candidates):
        for fmt in (
            "%Y-%m-%d",
            "%m/%d/%y",
            "%m/%d/%Y",
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%d-%b-%y",
            "%d-%B-%y",
            "%b %d %Y",
            "%B %d %Y",
            "%b %d, %Y",
            "%B %d, %Y",
        ):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def date_fragments(text: str) -> list[str]:
    patterns = (
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2}-[A-Za-z]{3,9}-\d{2,4}\b",
        r"\b[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4}\b",
    )
    fragments: list[str] = []
    for pattern in patterns:
        fragments.extend(match.group(0) for match in re.finditer(pattern, text))
    return fragments
