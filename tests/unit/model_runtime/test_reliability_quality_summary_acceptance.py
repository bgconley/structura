from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_report_acceptance_fails_when_quality_summary_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-quality-summary",
        title_prefix="Phase 8.5 Quality Summary",
        documents=_document_reports(),
    )
    report["qualitySummary"] = {
        "documents": 2,
        "reviewRequiredDocuments": 0,
        "reviewStatusCounts": {"filed": 3},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["qualitySummary"]["status"] == "failed"
    assert summary["checks"]["qualitySummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-quality-summary",
            "invalid": [
                "documents",
                "reviewRequiredDocuments",
                "reviewStatusCounts",
            ],
            "details": report["qualitySummary"],
            "recomputed": {
                "documents": 3,
                "reviewRequiredDocuments": 2,
                "reviewStatusCounts": {"filed": 2, "needs_review": 1},
            },
        }
    ]


def _document_reports() -> list[dict[str, Any]]:
    return [
        {
            "document": {
                "id": "doc-quality-direct-review",
                "document_family": "invoice",
                "review_status": "needs_review",
            },
            "semantic": [{"review_required": False}],
            "extractions": [{"review_status": "reviewed"}],
        },
        {
            "document": {
                "id": "doc-quality-extraction-review",
                "document_family": "receipt",
                "review_status": "filed",
            },
            "semantic": [{"review_required": False}],
            "extractions": [{"review_status": "needs_review"}],
        },
        {
            "document": {
                "id": "doc-quality-clean",
                "document_family": "statement",
                "review_status": "filed",
            },
            "semantic": [{"review_required": False}],
            "extractions": [{"review_status": "reviewed"}],
        },
    ]
