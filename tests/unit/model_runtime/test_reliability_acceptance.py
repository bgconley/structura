from __future__ import annotations

from copy import deepcopy

from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance


def test_report_acceptance_passes_for_resident_report_without_gold_metrics() -> None:
    summary = evaluate_phase85_report_acceptance([_resident_report()])

    assert summary["status"] == "passed"
    assert summary["checks"]["reportLineage"]["status"] == "passed"
    assert summary["checks"]["requiredSummaries"]["status"] == "passed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "passed"
    assert summary["checks"]["operationalSLOs"]["status"] == "passed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "not_required"
    assert summary["checks"]["repeatabilityFingerprints"]["status"] == "not_required"


def test_report_acceptance_fails_for_missing_report_lineage() -> None:
    report = _resident_report()
    report.pop("fixtureType")
    report["runManifest"].pop("model_mode")  # type: ignore[union-attr]

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["reportLineage"]["status"] == "failed"
    assert summary["checks"]["reportLineage"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "missing": ["fixtureType", "runManifest.model_mode"],
            "invalid": [],
        }
    ]


def test_report_acceptance_fails_for_missing_summaries_and_failed_gates() -> None:
    report = _resident_report()
    del report["plannerSummary"]
    report["acceptanceGates"]["hardCorrectnessInvariants"]["status"] = "failed"
    report["acceptanceGates"]["hardCorrectnessInvariants"]["totalViolationCount"] = 1

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["requiredSummaries"]["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "failed"


def test_report_acceptance_requires_gold_when_requested() -> None:
    summary = evaluate_phase85_report_acceptance([_resident_report()], require_gold=True)

    assert summary["status"] == "failed"
    assert summary["checks"]["goldCorpusQuality"]["status"] == "failed"


def test_report_acceptance_compares_repeatability_fingerprints_across_two_passes() -> None:
    first = _resident_report()
    second = deepcopy(first)
    second["runId"] = "phase85-pass-2"
    second["repeatabilityFingerprints"]["candidateFingerprints"] = "changed-candidates"

    summary = evaluate_phase85_report_acceptance([first, second])

    assert summary["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["status"] == "failed"
    assert summary["checks"]["repeatabilityFingerprints"]["drift"] == ["candidateFingerprints"]


def _resident_report() -> dict[str, object]:
    return {
        "runId": "phase85-pass-1",
        "fixtureType": "model_backed",
        "measuredAt": "2026-06-04T12:00:00+00:00",
        "runManifest": {
            "pipeline_version": "phase8_5_reliability_v1",
            "model_mode": "live",
        },
        "plannerSummary": {"selectedTaskCount": 2},
        "candidateAdmissionSummary": {"admittedCount": 2, "rejectedCount": 0},
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
            },
        },
    }
