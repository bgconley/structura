from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_report_acceptance_fails_when_retry_summary_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-retry-summary",
        title_prefix="Phase 8.5 Retry Summary",
        documents=[_document_report()],
    )
    report["retrySummary"] = {
        "outcomes": {"succeeded": 2},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["retrySummary"]["status"] == "failed"
    assert summary["checks"]["retrySummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-retry-summary",
            "invalid": ["outcomes"],
            "details": report["retrySummary"],
            "recomputed": {"outcomes": {"retry_skipped": 1, "succeeded": 1}},
        }
    ]


def test_report_retry_summary_normalizes_attempt_outcomes() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-retry-normalized-attempts",
        title_prefix="Phase 8.5 Retry Summary",
        documents=[_document_report_with_cased_attempt_outcomes()],
    )

    assert report["retrySummary"] == {
        "outcomes": {"retry_skipped": 1, "succeeded": 1},
    }

    report["retrySummary"] = {
        "outcomes": {" Retry_Skipped ": 1, " Succeeded ": 1},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["retrySummary"]["status"] == "failed"
    assert summary["checks"]["retrySummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-retry-normalized-attempts",
            "invalid": ["outcomes"],
            "details": report["retrySummary"],
            "recomputed": {"outcomes": {"retry_skipped": 1, "succeeded": 1}},
        }
    ]


def test_report_retry_summary_normalizes_job_status_fallback() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-retry-normalized-jobs",
        title_prefix="Phase 8.5 Retry Summary",
        documents=[_document_report_with_cased_job_statuses()],
    )

    assert report["retrySummary"] == {
        "outcomes": {"queued": 1, "succeeded": 2},
    }

    report["retrySummary"] = {
        "outcomes": {" Queued ": 1, " Succeeded ": 2},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["retrySummary"]["status"] == "failed"
    assert summary["checks"]["retrySummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-retry-normalized-jobs",
            "invalid": ["outcomes"],
            "details": report["retrySummary"],
            "recomputed": {"outcomes": {"queued": 1, "succeeded": 2}},
        }
    ]


def _document_report() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-retry-summary",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "extractions": [
            {
                "status": "completed",
                "review_status": "needs_review",
                "visual_input_attempts": [
                    {"outcome": "succeeded"},
                    {"status": "retry_skipped"},
                ],
            }
        ],
    }


def _document_report_with_cased_attempt_outcomes() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-retry-cased-attempts",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "extractions": [
            {
                "status": "completed",
                "review_status": "needs_review",
                "visualInputAttempts": [
                    {"outcome": " Succeeded "},
                    {"status": " Retry_Skipped "},
                ],
            }
        ],
    }


def _document_report_with_cased_job_statuses() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-retry-cased-jobs",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "jobs": [
            {
                "queue_name": "extraction",
                "job_type": "extract",
                "status": " Succeeded ",
                "count": 2,
            },
            {
                "queue_name": "semantic-annotations",
                "job_type": "semantic-annotations",
                "status": " Queued ",
                "count": 1,
            },
        ],
    }
