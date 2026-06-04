from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_gold_metrics import MAX_THRESHOLD_METRICS, REQUIRED_GOLD_METRICS
from lib.model_runtime.reliability_report import build_phase85_reliability_report
from lib.model_runtime.reliability_versions import PIPELINE_VERSION


def test_report_acceptance_requires_gold_when_requested() -> None:
    summary = evaluate_phase85_report_acceptance([_report()], require_gold=True)

    assert summary["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "failed"


def test_report_acceptance_fails_when_gold_gate_hides_metric_gaps() -> None:
    report = _report()
    report["acceptanceGates"]["goldCorpusQuality"] = {
        "status": "passed",
        "missingMetrics": ["fieldF1ByFamily"],
        "failedMetrics": ["duplicateRate"],
    }

    summary = evaluate_phase85_report_acceptance([report], require_gold=True)

    assert summary["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-gold-1",
            "status": "passed",
            "details": report["acceptanceGates"]["goldCorpusQuality"],
            "invalid": ["missingMetrics", "failedMetrics", "metrics"],
        }
    ]


def test_report_acceptance_fails_when_gold_gate_hides_metric_details() -> None:
    report = _report()
    report["acceptanceGates"]["goldCorpusQuality"] = {
        "status": "passed",
        "missingMetrics": [],
        "failedMetrics": [],
    }

    summary = evaluate_phase85_report_acceptance([report], require_gold=True)

    assert summary["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-gold-1",
            "status": "passed",
            "details": report["acceptanceGates"]["goldCorpusQuality"],
            "invalid": ["metrics"],
        }
    ]


def test_report_acceptance_fails_when_gold_gate_omits_required_metric_details() -> None:
    report = _report()
    report["acceptanceGates"]["goldCorpusQuality"] = {
        "status": "passed",
        "missingMetrics": [],
        "failedMetrics": [],
        "metrics": {
            REQUIRED_GOLD_METRICS[0]: {
                "status": "passed",
                "invalidThreshold": False,
                "invalidValues": [],
                "failingKeys": [],
            },
        },
    }

    summary = evaluate_phase85_report_acceptance([report], require_gold=True)

    assert summary["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-gold-1",
            "status": "passed",
            "details": report["acceptanceGates"]["goldCorpusQuality"],
            "invalid": ["metrics.requiredMetrics"],
        }
    ]


def test_report_acceptance_fails_when_gold_gate_omits_required_metric_scope() -> None:
    report = _report()
    report["acceptanceGates"]["goldCorpusQuality"] = {
        "status": "passed",
        "missingMetrics": [],
        "failedMetrics": [],
        "metrics": _passed_gold_metric_details(),
    }

    summary = evaluate_phase85_report_acceptance([report], require_gold=True)

    assert summary["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-gold-1",
            "status": "passed",
            "details": report["acceptanceGates"]["goldCorpusQuality"],
            "invalid": ["requiredMetrics"],
        }
    ]


def test_report_acceptance_fails_when_gold_gate_hides_failed_metric_detail() -> None:
    report = _report()
    report["acceptanceGates"]["goldCorpusQuality"] = {
        "status": "passed",
        "missingMetrics": [],
        "failedMetrics": [],
        "metrics": {
            "fieldF1ByFamily": {
                "status": "failed",
                "invalidThreshold": False,
                "invalidValues": [],
                "failingKeys": [{"key": "invoice", "value": 0.2}],
            },
            "duplicateRate": {
                "status": "passed",
                "invalidThreshold": True,
                "invalidValues": [],
                "failingKeys": [],
            },
            "fieldPrecisionByFamily": {
                "status": "passed",
                "invalidThreshold": False,
                "invalidValues": [{"key": "receipt", "reason": "non_finite"}],
                "failingKeys": [],
            },
        },
    }

    summary = evaluate_phase85_report_acceptance([report], require_gold=True)

    assert summary["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-gold-1",
            "status": "passed",
            "details": report["acceptanceGates"]["goldCorpusQuality"],
            "invalid": [
                "metrics.requiredMetrics",
                "metrics.duplicateRate.invalidThreshold",
                "metrics.fieldF1ByFamily.status",
                "metrics.fieldF1ByFamily.failingKeys",
                "metrics.fieldPrecisionByFamily.invalidValues",
            ],
        }
    ]


def test_report_acceptance_recomputes_gold_metrics_from_document_rows() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-gold-recompute",
        title_prefix="Phase 8.5 Gold Recompute",
        documents=[
            {
                "document": {"id": "doc-gold", "document_family": "invoice"},
                "goldMetrics": _passing_gold_metric_values(),
                "goldThresholds": _gold_metric_thresholds(),
            }
        ],
    )
    report["documents"][0]["goldMetrics"]["expectedCalibrationError"] = 0.5

    summary = evaluate_phase85_report_acceptance([report], require_gold=True)

    assert summary["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-gold-recompute",
            "status": "passed",
            "details": report["acceptanceGates"]["goldCorpusQuality"],
            "invalid": [
                "recomputed.failedMetrics",
                "recomputed.metrics.expectedCalibrationError.status",
                "recomputed.metrics.expectedCalibrationError.failingKeys",
            ],
            "recomputed": {
                "status": "failed",
                "missingMetrics": [],
                "failedMetrics": ["expectedCalibrationError"],
            },
        }
    ]


def _report() -> dict[str, Any]:
    return {
        "runId": "phase85-gold-1",
        "fixtureType": "deterministic_fixture",
        "measuredAt": "2026-06-04T12:00:00+00:00",
        "runManifest": {
            "run_id": "phase85-gold-1",
            "pipeline_version": PIPELINE_VERSION,
            "model_mode": "fixture",
        },
        "plannerSummary": {"selectedTaskCount": 2},
        "candidateAdmissionSummary": {"admittedCount": 2, "rejectedCount": 0},
        "contractSummary": {"contractedTaskCount": 2, "missingContractTaskCount": 0},
        "evidenceSummary": {"concreteEvidenceCoverage": 1.0},
        "dedupeSummary": {"totalDuplicateSuppressionCount": 0},
        "envelopeSummary": {"concreteEvidenceCoverage": 1.0},
        "visualInputPlanSummary": {"routeDistribution": {"full_page": 1}},
        "retrySummary": {"outcomes": {"succeeded": 1}},
        "extractionPressure": {"selectedTaskCount": 2},
        "safeOutcomeSummary": {"unsafeFailureCount": 0},
        "qualitySummary": {"documents": 1},
        "repeatabilityFingerprints": {
            "documentFamily": "doc-family",
            "semanticRegions": "semantic",
            "plannerTasks": "planner",
            "candidateFingerprints": "candidates",
            "canonicalOutput": "canonical",
            "reviewTasks": "review",
            "rejectionDistribution": "rejections",
        },
        "acceptanceGates": {
            "hardCorrectnessInvariants": {
                "status": "passed",
                "totalViolationCount": 0,
            },
            "goldCorpusQuality": {
                "status": "not_evaluated",
                "missingMetrics": [],
            },
            "operationalSLOs": {
                "status": "passed",
                "metrics": {
                    "targetQueueDeadLetterCount": 0,
                },
                "gates": _passed_operational_slo_gates(),
            },
        },
    }


def _passed_operational_slo_gates() -> dict[str, dict[str, object]]:
    return {
        "targetQueueDeadLetters": {"status": "passed", "violationCount": 0},
        "classifiedOperationalFailures": {"status": "passed", "violationCount": 0},
        "retrySuccessRate": {"status": "passed", "violationCount": 0},
        "runtimeFailureRates": {"status": "passed", "violationCount": 0},
        "runawayFanout": {"status": "passed", "violationCount": 0},
        "retrySafeJobs": {"status": "passed", "violationCount": 0},
    }


def _passed_gold_metric_details() -> dict[str, dict[str, object]]:
    return {
        metric: {
            "status": "passed",
            "invalidThreshold": False,
            "invalidValues": [],
            "failingKeys": [],
        }
        for metric in REQUIRED_GOLD_METRICS
    }


def _passing_gold_metric_values() -> dict[str, float]:
    return {
        metric: 0.0 if metric in MAX_THRESHOLD_METRICS else 0.95 for metric in REQUIRED_GOLD_METRICS
    }


def _gold_metric_thresholds() -> dict[str, float]:
    return {
        metric: 0.1 if metric in MAX_THRESHOLD_METRICS else 0.9 for metric in REQUIRED_GOLD_METRICS
    }
