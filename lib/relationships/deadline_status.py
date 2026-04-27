from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any


def deadline_status(
    *,
    due_on: date,
    confidence: object,
    evidence: list[dict[str, Any]],
) -> str:
    if not evidence:
        return "needs_review"
    confidence_value = _confidence_float(confidence)
    if confidence_value is not None and confidence_value < 0.65:
        return "needs_review"
    today = date.today()
    if due_on < today:
        return "overdue"
    if due_on <= today + timedelta(days=30):
        return "due_soon"
    return "open"


def remind_from(due_on: date) -> date:
    return due_on - timedelta(days=30)


def _confidence_float(confidence: object) -> float | None:
    if confidence is None:
        return None
    if isinstance(confidence, int | float | Decimal):
        return float(confidence)
    return None
