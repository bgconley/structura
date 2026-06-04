from __future__ import annotations

import math
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
    summaries: list[dict[str, Any]] = []
    for doc in documents:
        metrics = dict_value(get_value(doc, "goldMetrics", "gold_metrics"))
        thresholds = dict_value(get_value(doc, "goldThresholds", "gold_thresholds"))
        if metrics or thresholds:
            summaries.append(evaluate_gold_corpus_metrics(metrics, thresholds))
    if len(summaries) == 1:
        return summaries[0]
    if summaries:
        return _combine_gold_corpus_summaries(summaries)
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
        if detail.get("invalidThreshold"):
            raise SystemExit(f"Gold corpus {metric} has a non-finite or non-numeric threshold.")
        if detail.get("invalidValues"):
            raise SystemExit(f"Gold corpus {metric} has non-finite or non-numeric values.")
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
    values, invalid_values = _numeric_leaves(metrics[metric])
    threshold = _finite_number(thresholds[metric])
    worst = _worst_value(values, direction)
    failing = [
        {"key": key, "value": value}
        for key, value in values
        if threshold is not None and _violates(value, threshold, direction)
    ]
    return {
        "status": "failed"
        if not values or failing or invalid_values or threshold is None
        else "passed",
        "direction": direction,
        "threshold": threshold,
        "invalidThreshold": threshold is None,
        "worstValue": worst,
        "values": {key: value for key, value in values},
        "invalidValues": invalid_values,
        "failingKeys": failing,
    }


def _direction(metric: str) -> str:
    if metric in MAX_THRESHOLD_METRICS:
        return "max"
    return "min"


def _combine_gold_corpus_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    missing = _ordered_metric_names(
        {
            str(metric)
            for summary in summaries
            for metric in list(summary.get("missingMetrics") or [])
        }
    )
    metrics = {
        metric: _combine_metric_details(
            metric,
            [
                detail
                for summary in summaries
                if (detail := dict_value(dict_value(summary.get("metrics")).get(metric)))
            ],
        )
        for metric in REQUIRED_GOLD_METRICS
    }
    failed = _ordered_metric_names(
        {metric for metric, detail in metrics.items() if get_value(detail, "status") == "failed"}
    )
    status = "passed" if not missing and not failed else "failed"
    return {
        "status": status,
        "requiredMetrics": list(REQUIRED_GOLD_METRICS),
        "missingMetrics": missing,
        "failedMetrics": failed,
        "metrics": metrics,
    }


def _combine_metric_details(metric: str, details: list[dict[str, Any]]) -> dict[str, Any]:
    direction = _direction(metric)
    threshold = _first_finite_threshold(details)
    values: dict[str, float] = {}
    invalid_values: list[dict[str, str]] = []
    failing_keys: list[dict[str, Any]] = []
    invalid_threshold = False
    for index, detail in enumerate(details, start=1):
        invalid_threshold = invalid_threshold or bool(
            get_value(detail, "invalidThreshold", "invalid_threshold")
        )
        for key, value in dict_value(get_value(detail, "values")).items():
            if isinstance(value, int | float):
                values[f"source{index}.{key}"] = float(value)
        invalid_values.extend(
            _prefixed_detail_rows(
                index,
                list(detail.get("invalidValues") or []),
            )
        )
        failing_keys.extend(
            _prefixed_detail_rows(
                index,
                list(detail.get("failingKeys") or []),
            )
        )
    worst = _worst_value(list(values.items()), direction)
    return {
        "status": "failed"
        if not values or invalid_threshold or invalid_values or failing_keys
        else "passed",
        "direction": direction,
        "threshold": threshold,
        "invalidThreshold": invalid_threshold or threshold is None,
        "worstValue": worst,
        "values": values,
        "invalidValues": invalid_values,
        "failingKeys": failing_keys,
    }


def _first_finite_threshold(details: list[dict[str, Any]]) -> float | None:
    for detail in details:
        threshold = get_value(detail, "threshold")
        if isinstance(threshold, int | float) and math.isfinite(float(threshold)):
            return float(threshold)
    return None


def _prefixed_detail_rows(index: int, rows: list[Any]) -> list[dict[str, Any]]:
    prefixed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(get_value(row, "key") or "value")
        prefixed.append({**row, "key": f"source{index}.{key}"})
    return prefixed


def _ordered_metric_names(names: set[str]) -> list[str]:
    return [metric for metric in REQUIRED_GOLD_METRICS if metric in names]


def _numeric_leaves(
    value: Any, *, prefix: str = "value"
) -> tuple[list[tuple[str, float]], list[dict[str, str]]]:
    if isinstance(value, bool):
        return [], [{"key": prefix, "reason": "non_numeric"}]
    if isinstance(value, int | float):
        number = float(value)
        if not math.isfinite(number):
            return [], [{"key": prefix, "reason": "non_finite"}]
        return [(prefix, number)], []
    if isinstance(value, dict):
        leaves: list[tuple[str, float]] = []
        invalid: list[dict[str, str]] = []
        for key, item in sorted(value.items()):
            child_leaves, child_invalid = _numeric_leaves(item, prefix=str(key))
            leaves.extend(child_leaves)
            invalid.extend(child_invalid)
        return leaves, invalid
    return [], [{"key": prefix, "reason": "non_numeric"}]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _worst_value(values: list[tuple[str, float]], direction: str) -> float | None:
    if not values:
        return None
    numbers = [value for _, value in values]
    return max(numbers) if direction == "max" else min(numbers)


def _violates(value: float, threshold: float, direction: str) -> bool:
    if direction == "max":
        return value > threshold
    return value < threshold
