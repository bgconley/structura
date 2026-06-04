from __future__ import annotations

from typing import Any

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_report_acceptance_fails_when_safe_outcome_summary_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-safe-outcome",
        title_prefix="Phase 8.5 Safe Outcome",
        documents=[_document_report()],
    )
    report["safeOutcomeSummary"] = {
        "safeAbstentionCount": 0,
        "safeSkipCount": 0,
        "safeRejectionCount": 0,
        "unsafeFailureCount": 0,
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["safeOutcomeSummary"]["status"] == "failed"
    assert summary["checks"]["safeOutcomeSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-safe-outcome",
            "invalid": [
                "safeAbstentionCount",
                "safeSkipCount",
                "safeRejectionCount",
                "unsafeFailureCount",
            ],
            "details": report["safeOutcomeSummary"],
            "recomputed": {
                "safeAbstentionCount": 3,
                "safeSkipCount": 2,
                "safeRejectionCount": 2,
                "unsafeFailureCount": 1,
            },
        }
    ]


def test_safe_outcome_summary_scopes_failures_to_phase85_target_queues() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-safe-outcome",
        title_prefix="Phase 8.5 Safe Outcome",
        documents=[_document_report()],
    )

    assert report["safeOutcomeSummary"]["unsafeFailureCount"] == 1


def _document_report() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-safe-outcome",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "planner": [
            {
                "selected_task_count": 1,
                "skipped_task_count": 2,
                "abstention_count": 3,
                "missing_contract_count": 0,
                "missing_grounding_count": 0,
                "incompatible_schema_count": 0,
                "duplicate_suppressed_count": 0,
            }
        ],
        "admissionEvents": [
            {
                "id": "rejected-field",
                "document_id": "doc-safe-outcome",
                "decision": "rejected_placeholder",
                "candidate_fingerprint": "candidate-rejected-field",
                "candidate_gate_version": CANDIDATE_GATE_VERSION,
                "contract_registry_version": CONTRACT_REGISTRY_VERSION,
                "reasons": ["placeholder_value"],
            },
            {
                "id": "rejected-line-item",
                "document_id": "doc-safe-outcome",
                "decision": "rejected_duplicate",
                "candidate_fingerprint": "candidate-rejected-line-item",
                "candidate_gate_version": CANDIDATE_GATE_VERSION,
                "contract_registry_version": CONTRACT_REGISTRY_VERSION,
                "reasons": ["duplicate_candidate"],
            },
        ],
        "jobs": [
            {
                "queue_name": "ingest",
                "job_type": "housekeeping",
                "status": "failed",
                "count": 1,
                "retryable": True,
                "error_json": {"taxonomy_code": "maintenance_fixture_failure"},
            },
            {
                "queue_name": "relationships",
                "job_type": "housekeeping",
                "status": "failed",
                "count": 1,
                "retryable": True,
                "error_json": {"taxonomy_code": "maintenance_fixture_failure"},
            },
            {
                "queue_name": "extraction",
                "job_type": "extract",
                "status": "failed",
                "count": 1,
                "retryable": True,
                "error_json": {"taxonomy_code": "granite_runtime_failure"},
            },
        ],
    }
