from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report_normalization import dict_value, get_value

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
REPEATABILITY_KEYS = ("plannerTasks", "candidateFingerprints")

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
        "requiredSummaries": _required_summaries_check(reports),
        "hardCorrectnessInvariants": _gate_check(
            reports,
            "hardCorrectnessInvariants",
            required_status="passed",
        ),
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
    if len(reports) < 2:
        return {"status": "not_required", "drift": [], "baseline": {}}
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
        "comparisons": comparisons,
    }


def _gate(report: dict[str, Any], gate_name: str) -> dict[str, Any]:
    gates = dict_value(get_value(report, "acceptanceGates", "acceptance_gates"))
    return dict_value(get_value(gates, gate_name))
