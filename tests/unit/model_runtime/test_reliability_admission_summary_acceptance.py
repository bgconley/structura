from __future__ import annotations

from typing import Any

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report
from lib.semantic_annotations.extraction_plan_repository import PLANNER_VERSION


def test_report_acceptance_fails_when_candidate_admission_summary_lineage_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-admission-summary",
        title_prefix="Phase 8.5 Admission Summary",
        documents=[_document_report()],
    )
    report["candidateAdmissionSummary"] = {
        **report["candidateAdmissionSummary"],
        "runId": "phase85-other-run",
        "plannerVersion": "phase8_5-old-planner",
        "candidateGateVersion": "phase8_5-old-gate",
        "contractRegistryVersion": "phase8_5-old-contracts",
        "regionEnvelopeVersion": "phase8_5-old-envelope",
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["candidateAdmissionSummary"]["status"] == "failed"
    assert summary["checks"]["candidateAdmissionSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-admission-summary",
            "invalid": [
                "runId",
                "plannerVersion",
                "candidateGateVersion",
                "contractRegistryVersion",
                "regionEnvelopeVersion",
            ],
            "details": report["candidateAdmissionSummary"],
            "recomputed": {
                "runId": "phase85-admission-summary",
                "plannerVersion": report["runManifest"]["planner_version"],
                "candidateGateVersion": CANDIDATE_GATE_VERSION,
                "contractRegistryVersion": CONTRACT_REGISTRY_VERSION,
                "regionEnvelopeVersion": report["runManifest"]["region_envelope_version"],
                "admittedCount": 1,
                "rejectedCount": 1,
                "rejectionReasons": {"missing_concrete_evidence": 1},
                "duplicateSuppressionCount": 0,
            },
        }
    ]


def test_report_acceptance_fails_when_candidate_admission_summary_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-admission-summary",
        title_prefix="Phase 8.5 Admission Summary",
        documents=[_document_report()],
    )
    report["candidateAdmissionSummary"] = {
        **report["candidateAdmissionSummary"],
        "admittedCount": 2,
        "rejectedCount": 0,
        "rejectionReasons": {},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["candidateAdmissionSummary"]["status"] == "failed"
    assert summary["checks"]["candidateAdmissionSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-admission-summary",
            "invalid": ["admittedCount", "rejectedCount", "rejectionReasons"],
            "details": report["candidateAdmissionSummary"],
            "recomputed": {
                "runId": "phase85-admission-summary",
                "plannerVersion": report["runManifest"]["planner_version"],
                "candidateGateVersion": CANDIDATE_GATE_VERSION,
                "contractRegistryVersion": CONTRACT_REGISTRY_VERSION,
                "regionEnvelopeVersion": report["runManifest"]["region_envelope_version"],
                "admittedCount": 1,
                "rejectedCount": 1,
                "rejectionReasons": {"missing_concrete_evidence": 1},
                "duplicateSuppressionCount": 0,
            },
        }
    ]


def test_report_acceptance_normalizes_candidate_admission_summary_decisions() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-admission-summary",
        title_prefix="Phase 8.5 Admission Summary",
        documents=[_document_report_with_cased_decisions()],
    )
    report["candidateAdmissionSummary"] = {
        **report["candidateAdmissionSummary"],
        "admittedCount": 0,
        "rejectedCount": 0,
        "rejectionReasons": {},
        "duplicateSuppressionCount": 0,
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["candidateAdmissionSummary"]["status"] == "failed"
    assert summary["checks"]["candidateAdmissionSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-admission-summary",
            "invalid": [
                "admittedCount",
                "rejectedCount",
                "rejectionReasons",
                "duplicateSuppressionCount",
            ],
            "details": report["candidateAdmissionSummary"],
            "recomputed": {
                "runId": "phase85-admission-summary",
                "plannerVersion": report["runManifest"]["planner_version"],
                "candidateGateVersion": CANDIDATE_GATE_VERSION,
                "contractRegistryVersion": CONTRACT_REGISTRY_VERSION,
                "regionEnvelopeVersion": report["runManifest"]["region_envelope_version"],
                "admittedCount": 1,
                "rejectedCount": 2,
                "rejectionReasons": {
                    "duplicate_candidate_fingerprint": 1,
                    "missing_concrete_evidence": 1,
                },
                "duplicateSuppressionCount": 1,
            },
        }
    ]


def test_report_acceptance_normalizes_candidate_admission_rejection_reasons() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-admission-summary",
        title_prefix="Phase 8.5 Admission Summary",
        documents=[_document_report_with_cased_rejection_reasons()],
    )

    assert report["candidateAdmissionSummary"]["rejectionReasons"] == {
        "missing_concrete_evidence": 1,
    }

    report["candidateAdmissionSummary"] = {
        **report["candidateAdmissionSummary"],
        "rejectionReasons": {" Missing_Concrete_Evidence ": 1},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["candidateAdmissionSummary"]["status"] == "failed"
    assert summary["checks"]["candidateAdmissionSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-admission-summary",
            "invalid": ["rejectionReasons"],
            "details": report["candidateAdmissionSummary"],
            "recomputed": {
                "runId": "phase85-admission-summary",
                "plannerVersion": report["runManifest"]["planner_version"],
                "candidateGateVersion": CANDIDATE_GATE_VERSION,
                "contractRegistryVersion": CONTRACT_REGISTRY_VERSION,
                "regionEnvelopeVersion": report["runManifest"]["region_envelope_version"],
                "admittedCount": 1,
                "rejectedCount": 1,
                "rejectionReasons": {"missing_concrete_evidence": 1},
                "duplicateSuppressionCount": 0,
            },
        }
    ]


def _document_report() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-admission-summary",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "field",
                "candidate_fingerprint": "admitted-field-1",
                **_admission_event_telemetry(),
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "field_path": "invoice.total_amount",
                        "value": "42.00",
                        "evidence": [{"page_id": "page-1"}],
                    }
                },
            },
            {
                "decision": "rejected_missing_evidence",
                "candidate_kind": "field",
                "candidate_fingerprint": "rejected-field-1",
                **_admission_event_telemetry(),
                "reasons": ["missing_concrete_evidence"],
                "payload_json": {
                    "candidate": {
                        "field_path": "invoice.invoice_number",
                        "value": "INV-1",
                        "evidence": [],
                    }
                },
            },
        ],
    }


def _document_report_with_cased_decisions() -> dict[str, Any]:
    document = _document_report()
    document["admissionEvents"][0]["decision"] = " Admitted_Review_Required "
    document["admissionEvents"][1]["decision"] = " Rejected_Missing_Evidence "
    document["admissionEvents"].append(
        {
            "decision": " Rejected_Duplicate ",
            "candidate_kind": "field",
            "candidate_fingerprint": "duplicate-field-1",
            **_admission_event_telemetry(),
            "reasons": ["duplicate_candidate_fingerprint"],
            "payload_json": {
                "candidate": {
                    "field_path": "invoice.total_amount",
                    "value": "42.00",
                    "evidence": [{"page_id": "page-1"}],
                }
            },
        }
    )
    return document


def _document_report_with_cased_rejection_reasons() -> dict[str, Any]:
    document = _document_report()
    document["admissionEvents"][1]["reasons"] = [" Missing_Concrete_Evidence "]
    return document


def _admission_event_telemetry() -> dict[str, str]:
    return {
        "run_id": "phase85-admission-summary",
        "planner_version": PLANNER_VERSION,
        "candidate_gate_version": CANDIDATE_GATE_VERSION,
        "contract_registry_version": CONTRACT_REGISTRY_VERSION,
    }
