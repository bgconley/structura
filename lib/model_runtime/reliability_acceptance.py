from __future__ import annotations

from datetime import datetime
from typing import Any

from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
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
        "operationalSLOs": _gate_check(
            reports,
            "operationalSLOs",
            required_status="passed",
        ),
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
        run_manifest = dict_value(get_value(report, "runManifest", "run_manifest"))
        pipeline_version = get_value(run_manifest, "pipeline_version", "pipelineVersion")
        model_mode = get_value(run_manifest, "model_mode", "modelMode")

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
        if status != "passed":
            invalid.append("status")
        if get_value(gate, "totalViolationCount", "total_violation_count") != 0:
            invalid.append("totalViolationCount")
        if invalid:
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "status": status,
                    "details": gate,
                    "invalid": invalid,
                }
            )
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }


def _gold_check(reports: list[dict[str, Any]], *, require_gold: bool) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        gate = _gate(report, "goldCorpusQuality")
        status = str(get_value(gate, "status") or "missing")
        if status == "passed":
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


def _repeatability_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    missing_by_report: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
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
    if missing_by_report:
        return {
            "status": "failed",
            "drift": [],
            "baseline": {},
            "missingByReport": missing_by_report,
            "comparisons": [],
        }
    if len(reports) < 2:
        return {
            "status": "not_required",
            "drift": [],
            "baseline": {},
            "missingByReport": [],
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
        "comparisons": comparisons,
    }


def _gate(report: dict[str, Any], gate_name: str) -> dict[str, Any]:
    gates = dict_value(get_value(report, "acceptanceGates", "acceptance_gates"))
    return dict_value(get_value(gates, gate_name))
