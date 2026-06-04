from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lib.model_runtime.reliability_fingerprints import repeatability_fingerprints
from lib.model_runtime.reliability_gold_metrics import evaluate_gold_corpus_metrics_from_documents
from lib.model_runtime.reliability_invariants import evaluate_hard_correctness_invariants
from lib.model_runtime.reliability_manifest import PIPELINE_VERSION, build_phase85_run_manifest
from lib.model_runtime.reliability_operational_slos import evaluate_operational_slos
from lib.model_runtime.reliability_report_normalization import json_safe
from lib.model_runtime.reliability_summaries import (
    candidate_admission_summary,
    envelope_summary,
    extraction_pressure,
    planner_summary,
    quality_summary,
    retry_summary,
    safe_outcome_summary,
    visual_input_plan_summary,
)

__all__ = [
    "PIPELINE_VERSION",
    "build_phase85_reliability_report",
    "build_phase85_run_manifest",
]


def build_phase85_reliability_report(
    *,
    run_id: str,
    title_prefix: str,
    documents: list[dict[str, Any]],
    manifest_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_documents = json_safe(documents)
    report: dict[str, Any] = {
        "runId": run_id,
        "measuredAt": datetime.now(UTC).isoformat(),
        "titlePrefix": title_prefix,
        "runManifest": build_phase85_run_manifest(
            run_id=run_id,
            overrides=manifest_overrides,
        ),
        "documents": safe_documents,
    }
    report["plannerSummary"] = planner_summary(run_id, safe_documents)
    report["candidateAdmissionSummary"] = candidate_admission_summary(run_id, safe_documents)
    report["envelopeSummary"] = envelope_summary(safe_documents)
    report["visualInputPlanSummary"] = visual_input_plan_summary(safe_documents)
    report["retrySummary"] = retry_summary(safe_documents)
    report["extractionPressure"] = extraction_pressure(safe_documents)
    report["safeOutcomeSummary"] = safe_outcome_summary(
        report["plannerSummary"],
        report["candidateAdmissionSummary"],
        safe_documents,
    )
    report["qualitySummary"] = quality_summary(safe_documents)
    report["acceptanceGates"] = {
        "hardCorrectnessInvariants": evaluate_hard_correctness_invariants(safe_documents),
        "goldCorpusQuality": evaluate_gold_corpus_metrics_from_documents(safe_documents),
        "operationalSLOs": evaluate_operational_slos(safe_documents),
    }
    report["repeatabilityFingerprints"] = repeatability_fingerprints(
        safe_documents,
        report["candidateAdmissionSummary"],
    )
    return report
