from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_report_acceptance_fails_when_visual_plan_summary_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-visual-plan-summary",
        title_prefix="Phase 8.5 Visual Plan Summary",
        documents=[_document_report()],
    )
    report["visualInputPlanSummary"] = {
        "routeDistribution": {"full_page": 2},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["visualInputPlanSummary"]["status"] == "failed"
    assert summary["checks"]["visualInputPlanSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-visual-plan-summary",
            "invalid": ["routeDistribution"],
            "details": report["visualInputPlanSummary"],
            "recomputed": {"routeDistribution": {"crop": 1, "full_page": 1}},
        }
    ]


def _document_report() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-visual-plan-summary",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "extractions": [
            {
                "status": "completed",
                "review_status": "needs_review",
                "visual_plan": {"route": "full_page"},
            },
            {
                "status": "completed",
                "review_status": "needs_review",
                "visual_plan": {"selectedRoute": "crop"},
            },
        ],
    }
