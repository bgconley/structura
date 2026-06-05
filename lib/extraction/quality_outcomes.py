from __future__ import annotations

from typing import Literal

QualityOutcome = Literal[
    "extracted_cleanly",
    "needs_human_review",
    "insufficient_signal",
    "no_extraction_target",
    "pipeline_failed",
]

_OUTCOME_PRIORITY: dict[QualityOutcome, int] = {
    "extracted_cleanly": 0,
    "no_extraction_target": 1,
    "insufficient_signal": 2,
    "needs_human_review": 3,
    "pipeline_failed": 4,
}


def combine_quality_outcomes(outcomes: list[QualityOutcome]) -> QualityOutcome:
    if not outcomes:
        return "insufficient_signal"
    return max(outcomes, key=lambda outcome: _OUTCOME_PRIORITY[outcome])
