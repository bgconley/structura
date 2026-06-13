from __future__ import annotations

from collections import Counter
from typing import Any

from lib.model_runtime.reliability_acceptance_recompute import (
    recomputed_hard_invariants,
    recomputed_operational_slos,
    recomputed_repeatability_fingerprints,
    violating_hard_invariants_summary,
    violating_operational_slo_summary,
)
from lib.model_runtime.reliability_admission_summary_acceptance import (
    candidate_admission_summary_acceptance_check,
)
from lib.model_runtime.reliability_control_summary_acceptance import (
    contract_summary_acceptance_check,
    dedupe_summary_acceptance_check,
    evidence_summary_acceptance_check,
)
from lib.model_runtime.reliability_document_outcome_acceptance import (
    document_outcomes_acceptance_check,
)
from lib.model_runtime.reliability_envelope_summary_acceptance import (
    envelope_summary_acceptance_check,
)
from lib.model_runtime.reliability_extraction_pressure_acceptance import (
    extraction_pressure_acceptance_check,
)
from lib.model_runtime.reliability_gold_acceptance import gold_corpus_acceptance_check
from lib.model_runtime.reliability_planner_summary_acceptance import (
    planner_summary_acceptance_check,
)
from lib.model_runtime.reliability_quality_summary_acceptance import (
    quality_summary_acceptance_check,
)
from lib.model_runtime.reliability_report_lineage_acceptance import report_lineage_check
from lib.model_runtime.reliability_report_normalization import dict_value, get_value
from lib.model_runtime.reliability_retry_summary_acceptance import (
    retry_summary_acceptance_check,
)
from lib.model_runtime.reliability_safe_outcome_acceptance import (
    safe_outcome_summary_acceptance_check,
)
from lib.model_runtime.reliability_summary_acceptance_coverage import (
    REPORT_SUMMARY_ACCEPTANCE_COVERAGE,
    REQUIRED_REPORT_SUMMARIES,
    summary_acceptance_coverage_check,
)
from lib.model_runtime.reliability_visual_plan_summary_acceptance import (
    visual_input_plan_summary_acceptance_check,
)

REPEATABILITY_KEYS = (
    "documentFamily",
    "semanticRegions",
    "plannerTasks",
    "candidateFingerprints",
    "canonicalOutput",
    "reviewTasks",
    "rejectionDistribution",
)
REPEATABILITY_DRIFT_KEYS = (
    "documentFamily",
    "semanticRegions",
    "plannerTasks",
    "candidateFingerprints",
    "canonicalOutput",
    "reviewTasks",
)
OPERATIONAL_SLO_GATE_KEYS = (
    "targetQueueDeadLetters",
    "classifiedOperationalFailures",
    "retrySuccessRate",
    "runtimeFailureRates",
    "runawayFanout",
    "retrySafeJobs",
)

__all__ = [
    "REPORT_SUMMARY_ACCEPTANCE_COVERAGE",
    "REQUIRED_REPORT_SUMMARIES",
    "REPEATABILITY_DRIFT_KEYS",
    "REPEATABILITY_KEYS",
    "assert_phase85_report_acceptance",
    "evaluate_phase85_report_acceptance",
]


def evaluate_phase85_report_acceptance(
    reports: list[dict[str, Any]],
    *,
    require_gold: bool = False,
) -> dict[str, Any]:
    checks = {
        "reportLineage": report_lineage_check(reports, require_model_backed=require_gold),
        "requiredSummaries": _required_summaries_check(reports),
        "plannerSummary": planner_summary_acceptance_check(reports),
        "candidateAdmissionSummary": candidate_admission_summary_acceptance_check(reports),
        "contractSummary": contract_summary_acceptance_check(reports),
        "evidenceSummary": evidence_summary_acceptance_check(reports),
        "dedupeSummary": dedupe_summary_acceptance_check(reports),
        "envelopeSummary": envelope_summary_acceptance_check(reports),
        "visualInputPlanSummary": visual_input_plan_summary_acceptance_check(reports),
        "retrySummary": retry_summary_acceptance_check(reports),
        "extractionPressure": extraction_pressure_acceptance_check(reports),
        "safeOutcomeSummary": safe_outcome_summary_acceptance_check(reports),
        "qualitySummary": quality_summary_acceptance_check(reports),
        "documentOutcomes": document_outcomes_acceptance_check(reports),
        "hardCorrectnessInvariants": _hard_correctness_check(reports),
        "operationalSLOs": _operational_slo_check(reports),
        "goldCorpusQuality": gold_corpus_acceptance_check(reports, require_gold=require_gold),
        "repeatabilityFingerprints": _repeatability_check(reports),
    }
    checks["summaryAcceptanceCoverage"] = summary_acceptance_coverage_check(checks)
    return {
        "status": "passed"
        if all(check["status"] in {"passed", "not_required"} for check in checks.values())
        else "failed",
        "reportCount": len(reports),
        "checks": checks,
    }


def assert_phase85_report_acceptance(summary: dict[str, Any]) -> None:
    if summary.get("status") == "passed":
        return
    failed = [
        name
        for name, check in dict_value(summary.get("checks")).items()
        if dict_value(check).get("status") == "failed"
    ]
    reason = ", ".join(failed) if failed else "unknown"
    raise SystemExit(f"Phase 8.5 report acceptance failed: {reason}")


def _required_summaries_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    missing_by_report: list[dict[str, Any]] = []
    invalid_by_report: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        missing = [key for key in REQUIRED_REPORT_SUMMARIES if key not in report]
        if missing:
            missing_by_report.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "missing": missing,
                }
            )
        invalid = [
            key
            for key in REQUIRED_REPORT_SUMMARIES
            if key in report and (not isinstance(report[key], dict) or not report[key])
        ]
        if invalid:
            invalid_by_report.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "invalid": invalid,
                }
            )
    return {
        "status": "passed"
        if reports and not missing_by_report and not invalid_by_report
        else "failed",
        "missingByReport": missing_by_report,
        "invalidByReport": invalid_by_report,
    }


def _hard_correctness_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        gate = _gate(report, "hardCorrectnessInvariants")
        status = str(get_value(gate, "status") or "missing")
        invalid: list[str] = []
        recomputed = recomputed_hard_invariants(report)
        if status != "passed":
            invalid.append("status")
        if not _is_zero_number(get_value(gate, "totalViolationCount", "total_violation_count")):
            invalid.append("totalViolationCount")
        invalid.extend(_hard_invariant_detail_invalids(gate))
        if recomputed is not None and not _is_zero_number(
            get_value(recomputed, "totalViolationCount", "total_violation_count")
        ):
            invalid.append("recomputed.totalViolationCount")
        if invalid:
            failure = {
                "reportIndex": index,
                "runId": get_value(report, "runId", "run_id"),
                "status": status,
                "details": gate,
                "invalid": invalid,
            }
            if recomputed is not None:
                failure["recomputed"] = violating_hard_invariants_summary(recomputed)
            failures.append(failure)
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }


def _hard_invariant_detail_invalids(gate: dict[str, Any]) -> list[str]:
    invalid: list[str] = []
    invariants = dict_value(get_value(gate, "invariants"))
    for invariant_name, detail_value in sorted(invariants.items()):
        detail = dict_value(detail_value)
        status = get_value(detail, "status")
        if status is not None and status != "passed":
            invalid.append(f"invariants.{invariant_name}.status")
        violation_count = get_value(detail, "violationCount", "violation_count")
        if not _is_zero_number(violation_count):
            invalid.append(f"invariants.{invariant_name}.violationCount")
    return invalid


def _operational_slo_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        gate = _gate(report, "operationalSLOs")
        status = str(get_value(gate, "status") or "missing")
        metrics = dict_value(get_value(gate, "metrics"))
        gates = dict_value(get_value(gate, "gates"))
        invalid: list[str] = []
        recomputed = recomputed_operational_slos(report)
        if status != "passed":
            invalid.append("status")
        if not _is_zero_number(
            get_value(metrics, "targetQueueDeadLetterCount", "target_queue_dead_letter_count")
        ):
            invalid.append("metrics.targetQueueDeadLetterCount")
        recomputed_metrics = (
            dict_value(get_value(recomputed, "metrics")) if recomputed is not None else {}
        )
        recomputed_gates = (
            dict_value(get_value(recomputed, "gates")) if recomputed is not None else {}
        )
        if recomputed is not None and not _is_zero_number(
            get_value(
                recomputed_metrics,
                "targetQueueDeadLetterCount",
                "target_queue_dead_letter_count",
            )
        ):
            invalid.append("recomputed.metrics.targetQueueDeadLetterCount")
        for gate_key in OPERATIONAL_SLO_GATE_KEYS:
            subgate = dict_value(get_value(gates, gate_key))
            gate_status = get_value(subgate, "status")
            if gate_status != "passed":
                invalid.append(f"gates.{gate_key}.status")
            violation_count = get_value(subgate, "violationCount", "violation_count")
            if not _is_zero_number(violation_count):
                invalid.append(f"gates.{gate_key}.violationCount")
            recomputed_subgate = dict_value(get_value(recomputed_gates, gate_key))
            if recomputed is not None and recomputed_subgate:
                recomputed_status = get_value(recomputed_subgate, "status")
                if recomputed_status != "passed":
                    invalid.append(f"recomputed.gates.{gate_key}.status")
                recomputed_violation_count = get_value(
                    recomputed_subgate,
                    "violationCount",
                    "violation_count",
                )
                if not _is_zero_number(recomputed_violation_count):
                    invalid.append(f"recomputed.gates.{gate_key}.violationCount")
        if invalid:
            failure = {
                "reportIndex": index,
                "runId": get_value(report, "runId", "run_id"),
                "status": status,
                "details": gate,
                "invalid": invalid,
            }
            if recomputed is not None:
                failure["recomputed"] = violating_operational_slo_summary(recomputed)
            failures.append(failure)
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }


def _is_zero_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and value == 0


def _repeatability_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    missing_by_report: list[dict[str, Any]] = []
    mismatched_by_report: list[dict[str, Any]] = []
    missing_document_evidence_by_report: list[dict[str, Any]] = []
    missing_run_ids: list[dict[str, int]] = []
    run_ids: list[str] = []
    for index, report in enumerate(reports):
        run_id = get_value(report, "runId", "run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            missing_run_ids.append({"reportIndex": index})
        else:
            run_ids.append(run_id.strip())
        fingerprints = dict_value(get_value(report, "repeatabilityFingerprints"))
        missing = [key for key in REPEATABILITY_KEYS if not get_value(fingerprints, key)]
        if missing:
            missing_by_report.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "missing": missing,
                }
            )
        recomputed = recomputed_repeatability_fingerprints(report)
        if len(reports) >= 2 and not _has_document_evidence(report):
            missing_document_evidence_by_report.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                }
            )
        if recomputed is not None:
            mismatched = [
                key
                for key in REPEATABILITY_KEYS
                if get_value(fingerprints, key) is not None
                and get_value(fingerprints, key) != get_value(recomputed, key)
            ]
            if mismatched:
                mismatched_by_report.append(
                    {
                        "reportIndex": index,
                        "runId": get_value(report, "runId", "run_id"),
                        "mismatched": mismatched,
                    }
                )
    duplicate_run_ids = sorted(run_id for run_id, count in Counter(run_ids).items() if count > 1)
    if missing_by_report or mismatched_by_report or missing_run_ids or duplicate_run_ids:
        return {
            "status": "failed",
            "drift": [],
            "baseline": {},
            "missingByReport": missing_by_report,
            "mismatchedByReport": mismatched_by_report,
            "missingDocumentEvidenceByReport": [],
            "missingRunIds": missing_run_ids,
            "duplicateRunIds": duplicate_run_ids,
            "comparisons": [],
        }
    if len(reports) < 2:
        return {
            "status": "not_required",
            "drift": [],
            "baseline": {},
            "missingByReport": [],
            "mismatchedByReport": [],
            "missingDocumentEvidenceByReport": [],
            "missingRunIds": [],
            "duplicateRunIds": [],
            "comparisons": [],
        }
    baseline = dict_value(get_value(reports[0], "repeatabilityFingerprints"))
    drift: list[str] = []
    comparisons: list[dict[str, Any]] = []
    for key in REPEATABILITY_DRIFT_KEYS:
        baseline_value = get_value(baseline, key)
        values = [
            get_value(dict_value(get_value(report, "repeatabilityFingerprints")), key)
            for report in reports[1:]
        ]
        if any(value != baseline_value for value in values):
            drift.append(key)
        comparisons.append({"key": key, "baseline": baseline_value, "values": values})
    return {
        "status": "passed" if not drift and not missing_document_evidence_by_report else "failed",
        "drift": drift,
        "missingByReport": [],
        "mismatchedByReport": [],
        "missingDocumentEvidenceByReport": missing_document_evidence_by_report,
        "missingRunIds": [],
        "duplicateRunIds": [],
        "comparisons": comparisons,
    }


def _has_document_evidence(report: dict[str, Any]) -> bool:
    documents = get_value(report, "documents")
    return isinstance(documents, list) and any(isinstance(row, dict) for row in documents)


def _gate(report: dict[str, Any], gate_name: str) -> dict[str, Any]:
    gates = dict_value(get_value(report, "acceptanceGates", "acceptance_gates"))
    return dict_value(get_value(gates, gate_name))
