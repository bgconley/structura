from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report_normalization import dict_value, get_value

MIN_THRESHOLD_METRICS = frozenset(
    {
        "familyTop1Accuracy",
        "familyTop2Accuracy",
        "fieldPrecisionByFamily",
        "fieldRecallByFamily",
        "fieldF1ByFamily",
        "lineItemRowPrecisionByFamily",
        "lineItemRowRecallByFamily",
        "lineItemRowF1ByFamily",
        "amountDateNormalizationAccuracy",
        "evidenceLocatorCompleteness",
        "repeatabilityStability",
        "precisionAtConfidenceBuckets",
    }
)
MAX_THRESHOLD_METRICS = frozenset(
    {
        "duplicateRate",
        "reviewBurden",
        "falseCanonicalPromotionRate",
        "confidenceCalibrationByFamilyField",
        "expectedCalibrationError",
        "reviewBurdenAtConfidenceThresholds",
    }
)
REQUIRED_GOLD_METRICS = tuple(sorted(MIN_THRESHOLD_METRICS | MAX_THRESHOLD_METRICS))

__all__ = [
    "REQUIRED_GOLD_METRICS",
    "assert_gold_corpus_metrics_pass",
    "evaluate_gold_corpus_metrics",
    "evaluate_gold_corpus_metrics_from_documents",
]


def evaluate_gold_corpus_metrics(
    metrics: dict[str, Any] | None,
    thresholds: dict[str, Any] | None,
) -> dict[str, Any]:
    metric_values = metrics or {}
    threshold_values = thresholds or {}
    missing = [
        metric
        for metric in REQUIRED_GOLD_METRICS
        if metric not in metric_values or metric not in threshold_values
    ]
    results = {
        metric: _evaluate_metric(metric, metric_values, threshold_values)
        for metric in REQUIRED_GOLD_METRICS
        if metric in metric_values and metric in threshold_values
    }
    failed = [metric for metric, result in results.items() if result["status"] == "failed"]
    status = "passed" if not missing and not failed else "failed"
    if metrics is None and thresholds is None:
        status = "not_evaluated"
    return {
        "status": status,
        "requiredMetrics": list(REQUIRED_GOLD_METRICS),
        "missingMetrics": missing,
        "failedMetrics": failed,
        "metrics": results,
    }


def evaluate_gold_corpus_metrics_from_documents(
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    for doc in documents:
        metrics = dict_value(get_value(doc, "goldMetrics", "gold_metrics"))
        thresholds = dict_value(get_value(doc, "goldThresholds", "gold_thresholds"))
        if metrics or thresholds:
            return evaluate_gold_corpus_metrics(metrics, thresholds)
    return evaluate_gold_corpus_metrics(None, None)


def assert_gold_corpus_metrics_pass(summary: dict[str, Any]) -> None:
    missing = list(summary.get("missingMetrics") or [])
    if missing:
        raise SystemExit(f"Gold corpus metric missing: {missing[0]}")
    failed = list(summary.get("failedMetrics") or [])
    if failed:
        metric = failed[0]
        detail = dict_value(dict_value(summary.get("metrics")).get(metric))
        observed = detail.get("worstValue")
        threshold = detail.get("threshold")
        if not isinstance(observed, int | float) or not isinstance(threshold, int | float):
            raise SystemExit(f"Gold corpus {metric} has no numeric values to evaluate.")
        raise SystemExit(
            f"Gold corpus {metric} {float(observed):.4f} does not meet {float(threshold):.4f}."
        )


def _evaluate_metric(
    metric: str,
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    direction = _direction(metric)
    values = _numeric_leaves(metrics[metric])
    threshold = float(thresholds[metric])
    worst = _worst_value(values, direction)
    failing = [
        {"key": key, "value": value}
        for key, value in values
        if _violates(value, threshold, direction)
    ]
    return {
        "status": "failed" if not values or failing else "passed",
        "direction": direction,
        "threshold": threshold,
        "worstValue": worst,
        "values": {key: value for key, value in values},
        "failingKeys": failing,
    }


def _direction(metric: str) -> str:
    if metric in MAX_THRESHOLD_METRICS:
        return "max"
    return "min"


def _numeric_leaves(value: Any, *, prefix: str = "value") -> list[tuple[str, float]]:
    if isinstance(value, int | float):
        return [(prefix, float(value))]
    if isinstance(value, dict):
        leaves: list[tuple[str, float]] = []
        for key, item in sorted(value.items()):
            leaves.extend(_numeric_leaves(item, prefix=str(key)))
        return leaves
    return []


def _worst_value(values: list[tuple[str, float]], direction: str) -> float | None:
    if not values:
        return None
    numbers = [value for _, value in values]
    return max(numbers) if direction == "max" else min(numbers)


def _violates(value: float, threshold: float, direction: str) -> bool:
    if direction == "max":
        return value > threshold
    return value < threshold
