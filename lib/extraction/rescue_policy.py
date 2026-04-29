from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lib.extraction.models import ValidationReport
from lib.semantic_annotations.models import SemanticExtractionTask

RescueOutcome = Literal["review_only", "rescue_permitted_once", "pipeline_failed"]


@dataclass(frozen=True)
class RescuePolicyContext:
    allow_8b_rescue: bool
    validation: ValidationReport
    semantic_task: SemanticExtractionTask | None
    candidate_count: int
    prior_rescue_attempted: bool


@dataclass(frozen=True)
class RescuePolicyDecision:
    outcome: RescueOutcome
    failure_class: str
    reason: str


class RescuePolicy:
    def decide(self, context: RescuePolicyContext) -> RescuePolicyDecision:
        failure_class = _failure_class(context)
        if failure_class == "pipeline_failed":
            return RescuePolicyDecision(
                outcome="pipeline_failed",
                failure_class=failure_class,
                reason=(
                    "Runtime or contract failure must be handled by job retry/dead-letter logic."
                ),
            )
        if context.prior_rescue_attempted:
            return RescuePolicyDecision(
                outcome="review_only",
                failure_class=failure_class,
                reason="A rescue has already been attempted for this region and failure class.",
            )
        if not context.allow_8b_rescue:
            return RescuePolicyDecision(
                outcome="review_only",
                failure_class=failure_class,
                reason="User did not permit Qwen3-VL 8B rescue.",
            )
        if _recoverable_by_semantic_rescue(context, failure_class):
            return RescuePolicyDecision(
                outcome="rescue_permitted_once",
                failure_class=failure_class,
                reason=(
                    "User permitted one Qwen3-VL 8B rescue for this recoverable extraction issue."
                ),
            )
        return RescuePolicyDecision(
            outcome="review_only",
            failure_class=failure_class,
            reason="Issue should be reviewed without Qwen3-VL 8B rescue.",
        )


def _failure_class(context: RescuePolicyContext) -> str:
    if any(
        check.get("code") == "json_schema" and check.get("status") == "failed"
        for check in context.validation.checks
    ):
        return "pipeline_failed"
    if context.semantic_task is not None and context.candidate_count == 0:
        return "empty_required_target"
    if any(
        str(check.get("code", "")).endswith(".required.total")
        and check.get("status") in {"failed", "warning"}
        for check in context.validation.checks
    ):
        return "missing_required_field"
    if any("total" in str(check.get("code", "")) for check in context.validation.checks):
        return "unreconciled_totals"
    if (
        context.semantic_task is not None
        and context.semantic_task.confidence is not None
        and context.semantic_task.confidence < 0.7
    ):
        return "low_confidence_only"
    return "needs_review"


def _recoverable_by_semantic_rescue(
    context: RescuePolicyContext,
    failure_class: str,
) -> bool:
    if context.semantic_task is None:
        return False
    return failure_class in {
        "empty_required_target",
        "missing_required_field",
        "unreconciled_totals",
        "ambiguous_semantic_region",
        "poor_layout_signal",
        "misclassified_semantic_region",
    }
