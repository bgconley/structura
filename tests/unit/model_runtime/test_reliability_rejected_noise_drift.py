from __future__ import annotations

from typing import Any

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.region_envelope import REGION_ENVELOPE_VERSION
from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report
from lib.semantic_annotations.extraction_plan_repository import PLANNER_VERSION


def test_report_acceptance_keeps_rejected_noise_out_of_repeatability_drift() -> None:
    first = _report_with_rejected_noise(
        run_id="phase85-rejection-noise-1",
        rejected_fingerprint="rejected-prompt-echo",
        rejected_reasons=["prompt_or_schema_artifact"],
    )
    second = _report_with_rejected_noise(
        run_id="phase85-rejection-noise-2",
        rejected_fingerprint="rejected-missing-evidence",
        rejected_reasons=["missing_concrete_evidence"],
    )

    summary = evaluate_phase85_report_acceptance([first, second])

    repeatability = summary["checks"]["repeatabilityFingerprints"]
    assert repeatability["status"] == "passed"
    assert repeatability["drift"] == []
    assert (
        first["candidateAdmissionSummary"]["rejectionReasons"]
        != second["candidateAdmissionSummary"]["rejectionReasons"]
    )


def _report_with_rejected_noise(
    *,
    run_id: str,
    rejected_fingerprint: str,
    rejected_reasons: list[str],
) -> dict[str, Any]:
    return build_phase85_reliability_report(
        run_id=run_id,
        title_prefix="Phase 8.5 Rejection Noise",
        documents=[
            {
                "document": {
                    "id": "doc-rejection-noise",
                    "document_family": "invoice",
                    "review_status": "needs_review",
                },
                "admissionEvents": [
                    _admission_event(
                        run_id=run_id,
                        fingerprint="stable-admitted-field",
                        decision="admitted_review_required",
                        reasons=[],
                        value="10.00",
                    ),
                    _admission_event(
                        run_id=run_id,
                        fingerprint=rejected_fingerprint,
                        decision="rejected_quality",
                        reasons=rejected_reasons,
                        value="rejected noise",
                    ),
                ],
                "fields": [
                    {
                        "field_path": "invoice.total_amount",
                        "value": "10.00",
                        "status": "needs_review",
                    }
                ],
                "lineItems": [],
                "observations": [],
                "reviewTasks": [],
            }
        ],
    )


def _admission_event(
    *,
    run_id: str,
    fingerprint: str,
    decision: str,
    reasons: list[str],
    value: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "planner_version": PLANNER_VERSION,
        "candidate_gate_version": CANDIDATE_GATE_VERSION,
        "contract_registry_version": CONTRACT_REGISTRY_VERSION,
        "region_envelope_version": REGION_ENVELOPE_VERSION,
        "candidate_kind": "field",
        "candidate_fingerprint": fingerprint,
        "decision": decision,
        "reasons": reasons,
        "evidence_concrete": True,
        "payload_json": {
            "candidate": {
                "field_path": "invoice.total_amount",
                "value": value,
                "evidence": [{"page_id": "page-1"}],
            }
        },
    }
