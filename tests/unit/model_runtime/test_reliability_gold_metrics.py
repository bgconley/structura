from __future__ import annotations

import pytest

from lib.model_runtime.reliability_gold_metrics import (
    assert_gold_corpus_metrics_pass,
    evaluate_gold_corpus_metrics,
)
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_gold_corpus_metrics_pass_when_all_required_metrics_meet_thresholds() -> None:
    summary = evaluate_gold_corpus_metrics(_gold_metrics(), _gold_thresholds())

    assert summary["status"] == "passed"
    assert summary["missingMetrics"] == []
    assert summary["metrics"]["familyTop1Accuracy"]["status"] == "passed"
    assert summary["metrics"]["fieldPrecisionByFamily"]["worstValue"] == 0.91
    assert summary["metrics"]["expectedCalibrationError"]["direction"] == "max"
    assert summary["metrics"]["reviewBurdenAtConfidenceThresholds"]["worstValue"] == 0.22


def test_gold_corpus_metrics_fail_for_threshold_breaches_and_missing_calibration() -> None:
    metrics = _gold_metrics()
    metrics["duplicateRate"] = 0.11
    metrics.pop("confidenceCalibrationByFamilyField")

    summary = evaluate_gold_corpus_metrics(metrics, _gold_thresholds())

    assert summary["status"] == "failed"
    assert summary["missingMetrics"] == ["confidenceCalibrationByFamilyField"]
    assert summary["metrics"]["duplicateRate"]["status"] == "failed"
    assert summary["metrics"]["duplicateRate"]["direction"] == "max"


def test_gold_corpus_metrics_fail_for_non_finite_values_and_thresholds() -> None:
    metrics = _gold_metrics()
    thresholds = _gold_thresholds()
    metrics["fieldPrecisionByFamily"] = {"invoice": float("nan"), "receipt": 0.91}
    thresholds["duplicateRate"] = float("inf")

    summary = evaluate_gold_corpus_metrics(metrics, thresholds)

    assert summary["status"] == "failed"
    assert "fieldPrecisionByFamily" in summary["failedMetrics"]
    assert "duplicateRate" in summary["failedMetrics"]
    assert summary["metrics"]["fieldPrecisionByFamily"]["invalidValues"] == [
        {"key": "invoice", "reason": "non_finite"}
    ]
    assert summary["metrics"]["duplicateRate"]["invalidThreshold"] is True


def test_gold_corpus_assertion_reports_invalid_values_and_thresholds() -> None:
    metrics = _gold_metrics()
    metrics["fieldPrecisionByFamily"] = {"invoice": float("nan"), "receipt": 0.91}
    invalid_value_summary = evaluate_gold_corpus_metrics(metrics, _gold_thresholds())

    with pytest.raises(SystemExit, match="fieldPrecisionByFamily has non-finite"):
        assert_gold_corpus_metrics_pass(invalid_value_summary)

    thresholds = _gold_thresholds()
    thresholds["duplicateRate"] = float("inf")
    invalid_threshold_summary = evaluate_gold_corpus_metrics(_gold_metrics(), thresholds)

    with pytest.raises(SystemExit, match="duplicateRate has a non-finite"):
        assert_gold_corpus_metrics_pass(invalid_threshold_summary)


def test_reliability_report_includes_gold_metric_summary_when_documents_provide_gold() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-20260604-gold-001",
        title_prefix="Phase 8.5 Gold",
        documents=[
            {
                "document": {"id": "doc-gold"},
                "goldMetrics": _gold_metrics(),
                "goldThresholds": _gold_thresholds(),
            }
        ],
    )

    gold = report["acceptanceGates"]["goldCorpusQuality"]
    assert gold["status"] == "passed"
    assert gold["metrics"]["lineItemRowF1ByFamily"]["status"] == "passed"


def _gold_metrics() -> dict[str, object]:
    return {
        "familyTop1Accuracy": 0.92,
        "familyTop2Accuracy": 0.98,
        "fieldPrecisionByFamily": {"invoice": 0.93, "receipt": 0.91},
        "fieldRecallByFamily": {"invoice": 0.88, "receipt": 0.9},
        "fieldF1ByFamily": {"invoice": 0.9, "receipt": 0.905},
        "lineItemRowPrecisionByFamily": {"invoice": 0.94, "receipt": 0.9},
        "lineItemRowRecallByFamily": {"invoice": 0.86, "receipt": 0.88},
        "lineItemRowF1ByFamily": {"invoice": 0.895, "receipt": 0.89},
        "amountDateNormalizationAccuracy": 0.96,
        "evidenceLocatorCompleteness": 0.97,
        "duplicateRate": 0.02,
        "reviewBurden": 0.24,
        "falseCanonicalPromotionRate": 0.0,
        "repeatabilityStability": 0.99,
        "confidenceCalibrationByFamilyField": {
            "invoice.total_amount": 0.04,
            "receipt.total_amount": 0.05,
        },
        "expectedCalibrationError": 0.04,
        "precisionAtConfidenceBuckets": {
            "0.70-0.80": 0.82,
            "0.80-0.90": 0.91,
            "0.90-1.00": 0.96,
        },
        "reviewBurdenAtConfidenceThresholds": {
            "0.70": 0.22,
            "0.80": 0.18,
            "0.90": 0.1,
        },
    }


def _gold_thresholds() -> dict[str, object]:
    return {
        "familyTop1Accuracy": 0.9,
        "familyTop2Accuracy": 0.95,
        "fieldPrecisionByFamily": 0.9,
        "fieldRecallByFamily": 0.85,
        "fieldF1ByFamily": 0.88,
        "lineItemRowPrecisionByFamily": 0.88,
        "lineItemRowRecallByFamily": 0.85,
        "lineItemRowF1ByFamily": 0.88,
        "amountDateNormalizationAccuracy": 0.95,
        "evidenceLocatorCompleteness": 0.95,
        "duplicateRate": 0.05,
        "reviewBurden": 0.3,
        "falseCanonicalPromotionRate": 0.0,
        "repeatabilityStability": 0.98,
        "confidenceCalibrationByFamilyField": 0.08,
        "expectedCalibrationError": 0.05,
        "precisionAtConfidenceBuckets": 0.8,
        "reviewBurdenAtConfidenceThresholds": 0.25,
    }
