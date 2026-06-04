from __future__ import annotations

from typing import Any

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.region_envelope import REGION_ENVELOPE_VERSION
from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report
from lib.semantic_annotations.extraction_plan_repository import PLANNER_VERSION


def test_report_acceptance_fails_when_task15_control_summaries_are_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-control-summary",
        title_prefix="Phase 8.5 Control Summary",
        documents=[_document_report()],
    )
    report["contractSummary"] = {
        "runId": "phase85-control-summary",
        "contractRegistryVersion": CONTRACT_REGISTRY_VERSION,
        "contractedTaskCount": 2,
        "missingContractTaskCount": 0,
        "schemaCounts": {"granite_invoice_line_items.v1": 2},
        "contractResolutionModes": {"exact": 2},
    }
    report["evidenceSummary"] = {
        "candidateEvidenceConcreteCount": 2,
        "candidateEvidenceMissingCount": 0,
        "regionEnvelopeEvidenceCount": 1,
        "regionEnvelopeConcreteEvidenceCount": 1,
        "concreteEvidenceCoverage": 1.0,
    }
    report["dedupeSummary"] = {
        "plannerDuplicateSuppressedCount": 0,
        "admissionDuplicateRejectionCount": 0,
        "totalDuplicateSuppressionCount": 0,
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["contractSummary"]["status"] == "failed"
    assert summary["checks"]["evidenceSummary"]["status"] == "failed"
    assert summary["checks"]["dedupeSummary"]["status"] == "failed"


def test_report_acceptance_normalizes_cased_duplicate_rejection_decisions() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-control-summary",
        title_prefix="Phase 8.5 Control Summary",
        documents=[_document_report_with_cased_duplicate_rejection()],
    )
    report["dedupeSummary"] = {
        "plannerDuplicateSuppressedCount": 0,
        "admissionDuplicateRejectionCount": 0,
        "totalDuplicateSuppressionCount": 0,
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["dedupeSummary"]["status"] == "failed"
    assert summary["checks"]["dedupeSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-control-summary",
            "invalid": [
                "admissionDuplicateRejectionCount",
                "totalDuplicateSuppressionCount",
            ],
            "details": report["dedupeSummary"],
            "recomputed": {
                "plannerDuplicateSuppressedCount": 0,
                "admissionDuplicateRejectionCount": 1,
                "totalDuplicateSuppressionCount": 1,
            },
        }
    ]


def test_report_contract_summary_normalizes_contract_resolution_modes() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-control-summary",
        title_prefix="Phase 8.5 Control Summary",
        documents=[_document_report_with_cased_contract_modes()],
    )

    assert report["contractSummary"]["contractResolutionModes"] == {
        "exact": 1,
        "missing": 1,
    }

    report["contractSummary"] = {
        **report["contractSummary"],
        "contractResolutionModes": {" Exact ": 1, " Missing ": 1},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["contractSummary"]["status"] == "failed"
    assert summary["checks"]["contractSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-control-summary",
            "invalid": ["contractResolutionModes"],
            "details": report["contractSummary"],
            "recomputed": {
                "runId": "phase85-control-summary",
                "contractRegistryVersion": CONTRACT_REGISTRY_VERSION,
                "contractedTaskCount": 1,
                "missingContractTaskCount": 1,
                "schemaCounts": {"granite_invoice_line_items.v1": 1},
                "contractResolutionModes": {"exact": 1, "missing": 1},
            },
        }
    ]


def test_report_contract_summary_normalizes_schema_counts() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-control-summary",
        title_prefix="Phase 8.5 Control Summary",
        documents=[_document_report_with_cased_schema_name()],
    )

    assert report["contractSummary"]["schemaCounts"] == {
        "granite_invoice_line_items.v1": 1,
    }

    report["contractSummary"] = {
        **report["contractSummary"],
        "schemaCounts": {" Granite_Invoice_Line_Items.V1 ": 1},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["contractSummary"]["status"] == "failed"
    assert summary["checks"]["contractSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-control-summary",
            "invalid": ["schemaCounts"],
            "details": report["contractSummary"],
            "recomputed": {
                "runId": "phase85-control-summary",
                "contractRegistryVersion": CONTRACT_REGISTRY_VERSION,
                "contractedTaskCount": 1,
                "missingContractTaskCount": 1,
                "schemaCounts": {"granite_invoice_line_items.v1": 1},
                "contractResolutionModes": {"exact": 1, "missing": 1},
            },
        }
    ]


def _document_report() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-control-summary",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "planner": [{"duplicate_suppressed_count": 1}],
        "plannerTasks": [
            {
                "id": "task-selected",
                "status": "selected",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-1",
                "model_output_schema_name": "granite_invoice_line_items.v1",
                "compatibility_mode": "exact",
                "grounding_kind": "table",
                "page_number": 1,
                "task_json": {"grounding": {"table_id": "table-1", "page_id": "page-1"}},
            },
            {
                "id": "task-skipped",
                "status": "skipped_missing_contract",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-2",
                "model_output_schema_name": None,
                "compatibility_mode": "missing",
            },
        ],
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_fingerprint": "candidate-1",
                "evidence_concrete": True,
                **_admission_event_telemetry(),
            },
            {
                "decision": "rejected_duplicate",
                "candidate_fingerprint": "candidate-duplicate",
                "reasons": ["duplicate_candidate"],
                "evidence_concrete": False,
                **_admission_event_telemetry(),
            },
        ],
        "extractions": [
            {
                "review_status": "needs_review",
                "normalization_json": {
                    "regionEnvelope": {
                        "evidence": [
                            {"concrete": True},
                            {"concrete": False},
                        ]
                    }
                },
            }
        ],
    }


def _document_report_with_cased_contract_modes() -> dict[str, Any]:
    document = _document_report()
    document["plannerTasks"][0]["compatibility_mode"] = " Exact "
    document["plannerTasks"][1]["compatibility_mode"] = " Missing "
    return document


def _document_report_with_cased_schema_name() -> dict[str, Any]:
    document = _document_report()
    document["plannerTasks"][0]["model_output_schema_name"] = " Granite_Invoice_Line_Items.V1 "
    return document


def _document_report_with_cased_duplicate_rejection() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-control-summary",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "planner": [{"duplicate_suppressed_count": 0}],
        "admissionEvents": [
            {
                "decision": " Rejected_Duplicate ",
                "candidate_fingerprint": "candidate-duplicate",
                "reasons": ["duplicate_candidate"],
                "evidence_concrete": False,
                **_admission_event_telemetry(),
            },
        ],
    }


def _admission_event_telemetry() -> dict[str, str]:
    return {
        "run_id": "phase85-control-summary",
        "planner_version": PLANNER_VERSION,
        "candidate_gate_version": CANDIDATE_GATE_VERSION,
        "contract_registry_version": CONTRACT_REGISTRY_VERSION,
        "region_envelope_version": REGION_ENVELOPE_VERSION,
    }
