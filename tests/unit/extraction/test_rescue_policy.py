from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import ValidationReport
from lib.extraction.rescue_policy import RescuePolicy, RescuePolicyContext
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef


def test_rescue_policy_returns_review_only_without_user_permission() -> None:
    decision = RescuePolicy().decide(
        RescuePolicyContext(
            allow_8b_rescue=False,
            qwen8_enabled=False,
            validation=_validation("invoice.required.total", "failed"),
            semantic_task=_semantic_task(),
            candidate_count=0,
            prior_rescue_attempted=False,
        )
    )

    assert decision.outcome == "review_only"
    assert decision.failure_class == "empty_required_target"


def test_rescue_policy_returns_review_only_when_qwen8_disabled_even_with_user_permission() -> None:
    decision = RescuePolicy().decide(
        RescuePolicyContext(
            allow_8b_rescue=True,
            qwen8_enabled=False,
            validation=_validation("invoice.required.total", "failed"),
            semantic_task=_semantic_task(),
            candidate_count=0,
            prior_rescue_attempted=False,
        )
    )

    assert decision.outcome == "review_only"
    assert decision.reason == "Qwen3-VL 8B rescue is disabled for this runtime profile."


def test_rescue_policy_permits_one_recoverable_rescue_with_user_permission_when_enabled() -> None:
    decision = RescuePolicy().decide(
        RescuePolicyContext(
            allow_8b_rescue=True,
            qwen8_enabled=True,
            validation=_validation("invoice.required.total", "failed"),
            semantic_task=_semantic_task(),
            candidate_count=0,
            prior_rescue_attempted=False,
        )
    )

    assert decision.outcome == "rescue_permitted_once"
    assert decision.failure_class == "empty_required_target"


def test_rescue_policy_does_not_rescue_low_confidence_alone() -> None:
    decision = RescuePolicy().decide(
        RescuePolicyContext(
            allow_8b_rescue=True,
            qwen8_enabled=True,
            validation=_validation("confidence.low", "warning"),
            semantic_task=_semantic_task(confidence=0.42),
            candidate_count=2,
            prior_rescue_attempted=False,
        )
    )

    assert decision.outcome == "review_only"
    assert decision.failure_class == "low_confidence_only"


def test_rescue_policy_never_loops_after_prior_attempt() -> None:
    decision = RescuePolicy().decide(
        RescuePolicyContext(
            allow_8b_rescue=True,
            qwen8_enabled=True,
            validation=_validation("invoice.required.total", "failed"),
            semantic_task=_semantic_task(),
            candidate_count=0,
            prior_rescue_attempted=True,
        )
    )

    assert decision.outcome == "review_only"
    assert (
        decision.reason == "A rescue has already been attempted for this region and failure class."
    )


def _validation(code: str, status: str) -> ValidationReport:
    return ValidationReport(
        needs_review=True,
        checks=[{"code": code, "status": status, "message": code}],
    )


def _semantic_task(*, confidence: float | None = 0.8) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=uuid4(),
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=uuid4()),
        confidence=confidence,
    )
