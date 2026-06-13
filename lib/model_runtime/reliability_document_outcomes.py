from __future__ import annotations

from collections import Counter
from typing import Any

from lib.model_runtime.reliability_job_scope import is_phase85_target_failure
from lib.model_runtime.reliability_report_normalization import (
    bool_value,
    dict_value,
    get_value,
    int_value,
    list_value,
    normalized_decision,
    normalized_text,
    normalized_token,
)

VALID_RELEASE_OUTCOMES = frozenset(
    {
        "extracted_cleanly",
        "needs_human_review",
        "insufficient_signal",
        "no_extraction_target",
        "pipeline_failed",
    }
)
VALID_ABSTENTION_CLASSES = frozenset(
    {
        "not_abstained",
        "quality_insufficient_signal",
        "no_extraction_target",
        "runtime_failure",
    }
)
REQUIRED_OVERFITTING_GUARDS = (
    "pinnedCorpus",
    "privateHoldout",
    "syntheticAdversarial",
    "usedForPromptTuning",
    "reviewedBeforeDefaultFlip",
)


def document_outcomes_from_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_document_outcome(document) for document in documents]


def document_outcome_summary(document_outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    outcome_counts: Counter[str] = Counter()
    abstention_counts: Counter[str] = Counter()
    holdout_counts: Counter[str] = Counter()
    pipeline_failed = 0
    holdout_documents = 0
    adversarial_documents = 0
    prompt_tuned_holdouts = 0
    reviewed_holdouts = 0
    rows = [row for row in document_outcomes if isinstance(row, dict)]
    for row in rows:
        outcome = normalized_token(get_value(row, "releaseOutcome", "release_outcome"))
        abstention = normalized_token(get_value(row, "abstentionClass", "abstention_class"))
        holdout_label = normalized_token(get_value(row, "holdoutLabel", "holdout_label"))
        guards = dict_value(get_value(row, "overfittingGuards", "overfitting_guards"))
        if outcome:
            outcome_counts[outcome] += 1
        if abstention:
            abstention_counts[abstention] += 1
        if holdout_label:
            holdout_counts[holdout_label] += 1
        private_holdout = bool_value(get_value(guards, "privateHoldout", "private_holdout"))
        synthetic_adversarial = bool_value(
            get_value(guards, "syntheticAdversarial", "synthetic_adversarial")
        )
        if outcome == "pipeline_failed":
            pipeline_failed += 1
        if private_holdout:
            holdout_documents += 1
        if synthetic_adversarial:
            adversarial_documents += 1
        if private_holdout and bool_value(
            get_value(guards, "usedForPromptTuning", "used_for_prompt_tuning")
        ):
            prompt_tuned_holdouts += 1
        if private_holdout and bool_value(
            get_value(guards, "reviewedBeforeDefaultFlip", "reviewed_before_default_flip")
        ):
            reviewed_holdouts += 1
    return {
        "documentCount": len(rows),
        "outcomeCounts": dict(sorted(outcome_counts.items())),
        "abstentionClassCounts": dict(sorted(abstention_counts.items())),
        "holdoutLabelCounts": dict(sorted(holdout_counts.items())),
        "pipelineFailedCount": pipeline_failed,
        "holdoutDocumentCount": holdout_documents,
        "adversarialDocumentCount": adversarial_documents,
        "promptTunedHoldoutCount": prompt_tuned_holdouts,
        "reviewedHoldoutDocumentCount": reviewed_holdouts,
    }


def _document_outcome(report_document: dict[str, Any]) -> dict[str, Any]:
    document = dict_value(get_value(report_document, "document"))
    outcome = _release_outcome(report_document)
    return {
        "documentId": _document_id(report_document, document),
        "filename": get_value(
            document,
            "original_filename",
            "originalFilename",
            "filename",
        )
        or get_value(report_document, "filename"),
        "documentFamily": get_value(document, "document_family", "documentFamily"),
        "releaseOutcome": outcome,
        "abstentionClass": _abstention_class(outcome),
        "holdoutLabel": _holdout_label(report_document),
        "overfittingGuards": _overfitting_guards(report_document),
    }


def _document_id(report_document: dict[str, Any], document: dict[str, Any]) -> str | None:
    value = get_value(document, "id", "document_id", "documentId") or get_value(
        report_document,
        "document_id",
        "documentId",
    )
    return str(value) if value is not None else None


def _release_outcome(report_document: dict[str, Any]) -> str:
    if _has_pipeline_failure(report_document):
        return "pipeline_failed"
    if _requires_review(report_document):
        return "needs_human_review"
    if _has_candidate_output(report_document):
        return "extracted_cleanly"
    if _has_insufficient_signal(report_document):
        return "insufficient_signal"
    return "no_extraction_target"


def _abstention_class(outcome: str) -> str:
    if outcome == "pipeline_failed":
        return "runtime_failure"
    if outcome == "insufficient_signal":
        return "quality_insufficient_signal"
    if outcome == "no_extraction_target":
        return "no_extraction_target"
    return "not_abstained"


def _has_pipeline_failure(report_document: dict[str, Any]) -> bool:
    return any(
        is_phase85_target_failure(job)
        for job in list_value(get_value(report_document, "jobs"))
        if isinstance(job, dict)
    )


def _requires_review(report_document: dict[str, Any]) -> bool:
    document = dict_value(get_value(report_document, "document"))
    if normalized_text(get_value(document, "review_status", "reviewStatus")) == "needs_review":
        return True
    if any(
        bool_value(get_value(row, "review_required", "reviewRequired"))
        for row in list_value(get_value(report_document, "semantic"))
        if isinstance(row, dict)
    ):
        return True
    if any(
        normalized_text(get_value(row, "review_status", "reviewStatus")) == "needs_review"
        or bool_value(
            get_value(
                dict_value(get_value(row, "validation_json", "validationJson")),
                "needs_review",
            )
        )
        for row in list_value(get_value(report_document, "extractions"))
        if isinstance(row, dict)
    ):
        return True
    return any(
        normalized_text(get_value(row, "status")) == "needs_review"
        for key in ("fields", "lineItems", "observations")
        for row in list_value(get_value(report_document, key))
        if isinstance(row, dict)
    )


def _has_candidate_output(report_document: dict[str, Any]) -> bool:
    if any(
        normalized_decision(get_value(row, "decision")).startswith("admitted")
        for row in list_value(get_value(report_document, "admissionEvents"))
        if isinstance(row, dict)
    ):
        return True
    return any(
        list_value(get_value(report_document, key))
        for key in ("fields", "lineItems", "observations")
    )


def _has_insufficient_signal(report_document: dict[str, Any]) -> bool:
    for row in list_value(get_value(report_document, "planner")):
        if not isinstance(row, dict):
            continue
        if (
            int_value(get_value(row, "abstention_count", "abstentionCount"))
            or int_value(get_value(row, "missing_contract_count", "missingContractCount"))
            or int_value(get_value(row, "missing_grounding_count", "missingGroundingCount"))
            or int_value(get_value(row, "incompatible_schema_count", "incompatibleSchemaCount"))
        ):
            return True
    return False


def _holdout_label(report_document: dict[str, Any]) -> str:
    release_gate = dict_value(get_value(report_document, "releaseGate", "release_gate"))
    guards = _raw_overfitting_guards(report_document)
    label = (
        get_value(report_document, "holdoutLabel", "holdout_label")
        or get_value(release_gate, "holdoutLabel", "holdout_label")
        or get_value(guards, "corpusSlice", "corpus_slice", "holdoutLabel", "holdout_label")
    )
    return normalized_token(label) or "pinned_corpus"


def _overfitting_guards(report_document: dict[str, Any]) -> dict[str, bool]:
    guards = _raw_overfitting_guards(report_document)
    label = _holdout_label(report_document)
    private_holdout = bool_value(get_value(guards, "privateHoldout", "private_holdout")) or (
        "holdout" in label and "pinned" not in label
    )
    synthetic_adversarial = (
        bool_value(get_value(guards, "syntheticAdversarial", "synthetic_adversarial"))
        or "adversarial" in label
    )
    pinned_corpus = bool_value(get_value(guards, "pinnedCorpus", "pinned_corpus")) or (
        label in {"pinned", "pinned_corpus"}
    )
    return {
        "pinnedCorpus": pinned_corpus,
        "privateHoldout": private_holdout,
        "syntheticAdversarial": synthetic_adversarial,
        "usedForPromptTuning": bool_value(
            get_value(guards, "usedForPromptTuning", "used_for_prompt_tuning")
        ),
        "reviewedBeforeDefaultFlip": bool_value(
            get_value(guards, "reviewedBeforeDefaultFlip", "reviewed_before_default_flip")
        ),
    }


def _raw_overfitting_guards(report_document: dict[str, Any]) -> dict[str, Any]:
    release_gate = dict_value(get_value(report_document, "releaseGate", "release_gate"))
    return {
        **dict_value(get_value(release_gate, "overfittingGuards", "overfitting_guards")),
        **dict_value(get_value(report_document, "overfittingGuards", "overfitting_guards")),
    }
