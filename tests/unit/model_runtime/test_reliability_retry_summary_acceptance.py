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
