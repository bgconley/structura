from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)
from lib.model_runtime.reliability_acceptance_recompute import (
    recomputed_hard_invariants,
    recomputed_operational_slos,
    recomputed_repeatability_fingerprints,
    violating_hard_invariants_summary,
    violating_operational_slo_summary,
)
from lib.model_runtime.reliability_report_normalization import dict_value, get_value
from lib.model_runtime.reliability_versions import PIPELINE_VERSION

VALID_FIXTURE_TYPES = frozenset({"deterministic_fixture", "model_backed"})
VALID_MODEL_MODES = frozenset({"fixture", "live", "required"})
EXPECTED_LIVE_MODEL_PROFILES = {
    "semantic_profile": QWEN_SEMANTIC_PROFILE,
    "granite_profile": GRANITE_VISION_PROFILE,
    "text_embedding_profile": TEXT_EMBED_PROFILE,
    "visual_embedding_profile": VISUAL_EMBED_PROFILE,
}
REQUIRED_REPORT_SUMMARIES = (
    "runManifest",
    "plannerSummary",
    "candidateAdmissionSummary",
    "envelopeSummary",
    "visualInputPlanSummary",
    "retrySummary",
    "extractionPressure",
    "safeOutcomeSummary",
    "qualitySummary",
    "repeatabilityFingerprints",
    "acceptanceGates",
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
OPERATIONAL_SLO_GATE_KEYS = (
    "targetQueueDeadLetters",
    "classifiedOperationalFailures",
    "retrySuccessRate",
    "runtimeFailureRates",
    "runawayFanout",
    "retrySafeJobs",
)

__all__ = [
    "REQUIRED_REPORT_SUMMARIES",
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
        "reportLineage": _report_lineage_check(reports),
        "requiredSummaries": _required_summaries_check(reports),
        "hardCorrectnessInvariants": _hard_correctness_check(reports),
        "operationalSLOs": _operational_slo_check(reports),
        "goldCorpusQuality": _gold_check(reports, require_gold=require_gold),
        "repeatabilityFingerprints": _repeatability_check(reports),
    }
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


def _report_lineage_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        missing: list[str] = []
        invalid: list[str] = []
        fixture_type = get_value(report, "fixtureType", "fixture_type")
        measured_at = get_value(report, "measuredAt", "measured_at")
        run_id = get_value(report, "runId", "run_id")
        run_manifest = dict_value(get_value(report, "runManifest", "run_manifest"))
        manifest_run_id = get_value(run_manifest, "run_id", "runId")
        pipeline_version = get_value(run_manifest, "pipeline_version", "pipelineVersion")
        model_mode = get_value(run_manifest, "model_mode", "modelMode")

        if not isinstance(run_id, str) or not run_id.strip():
            missing.append("runId")

        if not isinstance(manifest_run_id, str) or not manifest_run_id.strip():
            missing.append("runManifest.run_id")
        elif (
            isinstance(run_id, str) and run_id.strip() and run_id.strip() != manifest_run_id.strip()
        ):
            invalid.append("runId/runManifest.run_id")

        if not isinstance(fixture_type, str) or not fixture_type.strip():
            missing.append("fixtureType")
        elif fixture_type.strip() not in VALID_FIXTURE_TYPES:
            invalid.append("fixtureType")

        if not isinstance(measured_at, str) or not measured_at.strip():
            missing.append("measuredAt")
        elif _parse_report_timestamp(measured_at) is None:
            invalid.append("measuredAt")

        if pipeline_version in (None, ""):
            missing.append("runManifest.pipeline_version")
        elif pipeline_version != PIPELINE_VERSION:
            invalid.append("runManifest.pipeline_version")

        if not isinstance(model_mode, str) or not model_mode.strip():
            missing.append("runManifest.model_mode")
        elif model_mode.strip() not in VALID_MODEL_MODES:
            invalid.append("runManifest.model_mode")

        if isinstance(fixture_type, str) and isinstance(model_mode, str):
            expected_fixture_type = (
                "model_backed"
                if model_mode.strip() in {"live", "required"}
                else "deterministic_fixture"
            )
            if fixture_type.strip() != expected_fixture_type:
                invalid.append("fixtureType/runManifest.model_mode")

        if isinstance(model_mode, str) and model_mode.strip() in {"live", "required"}:
            for profile_key, expected_profile in EXPECTED_LIVE_MODEL_PROFILES.items():
                actual_profile = get_value(run_manifest, profile_key, _camelize(profile_key))
                lineage_name = f"runManifest.{profile_key}"
                if not isinstance(actual_profile, str) or not actual_profile.strip():
                    missing.append(lineage_name)
                elif actual_profile.strip() != expected_profile:
                    invalid.append(lineage_name)

        if missing or invalid:
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "missing": missing,
                    "invalid": invalid,
                }
            )
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }


def _camelize(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _parse_report_timestamp(value: str) -> datetime | None:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _required_summaries_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    missing_by_report: list[dict[str, Any]] = []
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
    return {
        "status": "passed" if reports and not missing_by_report else "failed",
        "missingByReport": missing_by_report,
    }


def _gate_check(
    reports: list[dict[str, Any]],
    gate_name: str,
    *,
    required_status: str,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        gate = _gate(report, gate_name)
        status = str(get_value(gate, "status") or "missing")
        if status != required_status:
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "status": status,
                    "details": gate,
                }
            )
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
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


def _gold_check(reports: list[dict[str, Any]], *, require_gold: bool) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        gate = _gate(report, "goldCorpusQuality")
        status = str(get_value(gate, "status") or "missing")
        if status == "passed":
            invalid = _gold_metric_failure_keys(gate)
            if not invalid:
                continue
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "status": status,
                    "details": gate,
                    "invalid": invalid,
                }
            )
            continue
        if not require_gold and status == "not_evaluated":
            continue
        failures.append(
            {
                "reportIndex": index,
                "runId": get_value(report, "runId", "run_id"),
                "status": status,
                "details": gate,
            }
        )
    if not require_gold and not failures:
        return {"status": "not_required", "failures": []}
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }


def _gold_metric_failure_keys(gate: dict[str, Any]) -> list[str]:
    invalid: list[str] = []
    missing_metrics = get_value(gate, "missingMetrics", "missing_metrics")
    failed_metrics = get_value(gate, "failedMetrics", "failed_metrics")
    if not isinstance(missing_metrics, list) or missing_metrics:
        invalid.append("missingMetrics")
    if not isinstance(failed_metrics, list) or failed_metrics:
        invalid.append("failedMetrics")
    metrics = dict_value(get_value(gate, "metrics"))
    for metric, detail_value in sorted(metrics.items()):
        detail = dict_value(detail_value)
        status = get_value(detail, "status")
        if status != "passed":
            invalid.append(f"metrics.{metric}.status")
        if get_value(detail, "invalidThreshold", "invalid_threshold"):
            invalid.append(f"metrics.{metric}.invalidThreshold")
        invalid_values = get_value(detail, "invalidValues", "invalid_values")
        if isinstance(invalid_values, list) and invalid_values:
            invalid.append(f"metrics.{metric}.invalidValues")
        failing_keys = get_value(detail, "failingKeys", "failing_keys")
        if isinstance(failing_keys, list) and failing_keys:
            invalid.append(f"metrics.{metric}.failingKeys")
    return invalid


def _repeatability_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    missing_by_report: list[dict[str, Any]] = []
    mismatched_by_report: list[dict[str, Any]] = []
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
            "missingRunIds": [],
            "duplicateRunIds": [],
            "comparisons": [],
        }
    baseline = dict_value(get_value(reports[0], "repeatabilityFingerprints"))
    drift: list[str] = []
    comparisons: list[dict[str, Any]] = []
    for key in REPEATABILITY_KEYS:
        baseline_value = get_value(baseline, key)
        values = [
            get_value(dict_value(get_value(report, "repeatabilityFingerprints")), key)
            for report in reports[1:]
        ]
        if any(value != baseline_value for value in values):
            drift.append(key)
        comparisons.append({"key": key, "baseline": baseline_value, "values": values})
    return {
        "status": "passed" if not drift else "failed",
        "drift": drift,
        "missingByReport": [],
        "mismatchedByReport": [],
        "missingRunIds": [],
        "duplicateRunIds": [],
        "comparisons": comparisons,
    }


def _gate(report: dict[str, Any], gate_name: str) -> dict[str, Any]:
    gates = dict_value(get_value(report, "acceptanceGates", "acceptance_gates"))
    return dict_value(get_value(gates, gate_name))
