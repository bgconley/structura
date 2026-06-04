from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.model_runtime.reliability_acceptance_recompute import (
    recomputed_contract_summary,
    recomputed_dedupe_summary,
    recomputed_evidence_summary,
)
from lib.model_runtime.reliability_report_normalization import dict_value, get_value, snake

_CONTRACT_SUMMARY_KEYS = (
    "runId",
    "contractRegistryVersion",
    "contractedTaskCount",
    "missingContractTaskCount",
    "schemaCounts",
    "contractResolutionModes",
)
_EVIDENCE_SUMMARY_KEYS = (
    "candidateEvidenceConcreteCount",
    "candidateEvidenceMissingCount",
    "regionEnvelopeEvidenceCount",
    "regionEnvelopeConcreteEvidenceCount",
    "concreteEvidenceCoverage",
)
_DEDUPE_SUMMARY_KEYS = (
    "plannerDuplicateSuppressedCount",
    "admissionDuplicateRejectionCount",
    "totalDuplicateSuppressionCount",
)


def contract_summary_acceptance_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return _summary_acceptance_check(
        reports,
        summary_key="contractSummary",
        keys=_CONTRACT_SUMMARY_KEYS,
        recompute=recomputed_contract_summary,
    )


def evidence_summary_acceptance_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return _summary_acceptance_check(
        reports,
        summary_key="evidenceSummary",
        keys=_EVIDENCE_SUMMARY_KEYS,
        recompute=recomputed_evidence_summary,
    )


def dedupe_summary_acceptance_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return _summary_acceptance_check(
        reports,
        summary_key="dedupeSummary",
        keys=_DEDUPE_SUMMARY_KEYS,
        recompute=recomputed_dedupe_summary,
    )


def _summary_acceptance_check(
    reports: list[dict[str, Any]],
    *,
    summary_key: str,
    keys: tuple[str, ...],
    recompute: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        summary = dict_value(get_value(report, summary_key))
        recomputed = recompute(report)
        if recomputed is None:
            continue
        invalid = [
            key
            for key in keys
            if get_value(summary, key, snake(key)) != get_value(recomputed, key, snake(key))
        ]
        if invalid:
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "invalid": invalid,
                    "details": summary,
                    "recomputed": recomputed,
                }
            )
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }
