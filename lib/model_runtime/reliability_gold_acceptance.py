from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_gold_metrics import REQUIRED_GOLD_METRICS
from lib.model_runtime.reliability_report_normalization import dict_value, get_value

__all__ = ["gold_corpus_acceptance_check"]


def gold_corpus_acceptance_check(
    reports: list[dict[str, Any]],
    *,
    require_gold: bool,
) -> dict[str, Any]:
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


def _gate(report: dict[str, Any], gate_name: str) -> dict[str, Any]:
    return dict_value(dict_value(get_value(report, "acceptanceGates")).get(gate_name))


def _gold_metric_failure_keys(gate: dict[str, Any]) -> list[str]:
    invalid: list[str] = []
    missing_metrics = get_value(gate, "missingMetrics", "missing_metrics")
    failed_metrics = get_value(gate, "failedMetrics", "failed_metrics")
    if not isinstance(missing_metrics, list) or missing_metrics:
        invalid.append("missingMetrics")
    if not isinstance(failed_metrics, list) or failed_metrics:
        invalid.append("failedMetrics")
    metrics_value = get_value(gate, "metrics")
    metrics = dict_value(metrics_value)
    if not isinstance(metrics_value, dict) or not metrics:
        invalid.append("metrics")
    elif any(metric not in metrics for metric in REQUIRED_GOLD_METRICS):
        invalid.append("metrics.requiredMetrics")
    elif get_value(gate, "requiredMetrics", "required_metrics") != list(REQUIRED_GOLD_METRICS):
        invalid.append("requiredMetrics")
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
