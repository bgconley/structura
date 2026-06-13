from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_document_outcomes import (
    REQUIRED_OVERFITTING_GUARDS,
    VALID_ABSTENTION_CLASSES,
    VALID_RELEASE_OUTCOMES,
    document_outcome_summary,
)
from lib.model_runtime.reliability_report_normalization import (
    bool_value,
    dict_value,
    get_value,
    normalized_text,
    normalized_token,
)


def document_outcomes_acceptance_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        rows = _document_outcome_rows(report)
        if not rows:
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "invalid": ["documentOutcomes"],
                    "details": get_value(report, "documentOutcomes", "document_outcomes"),
                }
            )
            continue
        row_failures = _row_failures(index, report, rows)
        failures.extend(row_failures)
        if row_failures:
            continue
        failures.extend(_summary_failures(index, report, rows))
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }


def _document_outcome_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    value = get_value(report, "documentOutcomes", "document_outcomes")
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _row_failures(
    report_index: int,
    report: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        invalid: list[str] = []
        outcome = normalized_token(get_value(row, "releaseOutcome", "release_outcome"))
        abstention = normalized_token(get_value(row, "abstentionClass", "abstention_class"))
        holdout_label = normalized_token(get_value(row, "holdoutLabel", "holdout_label"))
        guards = get_value(row, "overfittingGuards", "overfitting_guards")
        if outcome not in VALID_RELEASE_OUTCOMES:
            invalid.append(f"documentOutcomes[{row_index}].releaseOutcome")
        if abstention not in VALID_ABSTENTION_CLASSES:
            invalid.append(f"documentOutcomes[{row_index}].abstentionClass")
        if not holdout_label:
            invalid.append(f"documentOutcomes[{row_index}].holdoutLabel")
        if not isinstance(guards, dict):
            invalid.append(f"documentOutcomes[{row_index}].overfittingGuards")
        else:
            for guard_key in REQUIRED_OVERFITTING_GUARDS:
                value = get_value(guards, guard_key)
                if not isinstance(value, bool):
                    invalid.append(f"documentOutcomes[{row_index}].overfittingGuards.{guard_key}")
        if invalid:
            failures.append(
                {
                    "reportIndex": report_index,
                    "runId": get_value(report, "runId", "run_id"),
                    "invalid": invalid,
                    "details": row,
                }
            )
    return failures


def _summary_failures(
    report_index: int,
    report: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summary = dict_value(get_value(report, "documentOutcomeSummary", "document_outcome_summary"))
    recomputed = document_outcome_summary(rows)
    if summary != recomputed:
        return [
            {
                "reportIndex": report_index,
                "runId": get_value(report, "runId", "run_id"),
                "invalid": ["documentOutcomeSummary"],
                "details": summary,
                "recomputed": recomputed,
            }
        ]
    invalid: list[str] = []
    if (
        normalized_text(get_value(report, "fixtureType", "fixture_type")) == "model_backed"
        and not get_value(summary, "holdoutDocumentCount")
        and not get_value(summary, "adversarialDocumentCount")
    ):
        invalid.append("modelBackedHoldoutOrAdversarialSlice")
    if get_value(summary, "promptTunedHoldoutCount"):
        invalid.append("overfittingGuards.usedForPromptTuning")
    if get_value(summary, "pipelineFailedCount") and not _failure_injection_enabled(report):
        invalid.append("pipelineFailedWithoutFailureInjection")
    if _default_flip_candidate(report) and _has_unreviewed_holdout(rows):
        invalid.append("overfittingGuards.reviewedBeforeDefaultFlip")
    if not invalid:
        return []
    return [
        {
            "reportIndex": report_index,
            "runId": get_value(report, "runId", "run_id"),
            "invalid": invalid,
            "details": summary,
        }
    ]


def _failure_injection_enabled(report: dict[str, Any]) -> bool:
    manifest = dict_value(get_value(report, "runManifest", "run_manifest"))
    for value in (
        get_value(report, "failureInjection", "failure_injection"),
        get_value(manifest, "failureInjection", "failure_injection"),
    ):
        if isinstance(value, dict):
            if bool_value(get_value(value, "enabled")):
                return True
        elif bool_value(value):
            return True
    return False


def _default_flip_candidate(report: dict[str, Any]) -> bool:
    manifest = dict_value(get_value(report, "runManifest", "run_manifest"))
    return bool_value(get_value(report, "defaultFlipCandidate", "default_flip_candidate")) or (
        bool_value(get_value(manifest, "defaultFlipCandidate", "default_flip_candidate"))
    )


def _has_unreviewed_holdout(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        guards = dict_value(get_value(row, "overfittingGuards", "overfitting_guards"))
        is_holdout = bool_value(get_value(guards, "privateHoldout", "private_holdout"))
        is_adversarial = bool_value(
            get_value(guards, "syntheticAdversarial", "synthetic_adversarial")
        )
        reviewed = bool_value(
            get_value(guards, "reviewedBeforeDefaultFlip", "reviewed_before_default_flip")
        )
        if (is_holdout or is_adversarial) and not reviewed:
            return True
    return False
