from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_report_acceptance_fails_when_envelope_summary_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-envelope-summary",
        title_prefix="Phase 8.5 Envelope Summary",
        documents=[_document_report()],
    )
    report["envelopeSummary"] = {
        **report["envelopeSummary"],
        "lineItems": 0,
        "tableRows": 0,
        "concreteEvidenceCoverage": 1.0,
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["envelopeSummary"]["status"] == "failed"
    assert summary["checks"]["envelopeSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-envelope-summary",
            "invalid": ["lineItems", "tableRows", "concreteEvidenceCoverage"],
            "details": report["envelopeSummary"],
            "recomputed": {
                "facts": 1,
                "lineItems": 2,
                "tableRows": 3,
                "observations": 1,
                "concreteEvidenceCoverage": 0.75,
            },
        }
    ]


def _document_report() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-envelope-summary",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "extractions": [
            {
                "status": "completed",
                "review_status": "needs_review",
                "normalization_json": {
                    "regionEnvelope": {
                        "facts": [{"field_path": "invoice.total_amount"}],
                        "line_items": [{}, {}],
                        "table_rows": [{}, {}, {}],
                        "observations": [{}],
                        "evidence": [
                            {"concrete": True},
                            {"concrete": True},
                            {"concrete": True},
                            {"concrete": False},
                        ],
                    }
                },
            }
        ],
    }
