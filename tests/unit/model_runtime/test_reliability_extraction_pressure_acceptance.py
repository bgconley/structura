from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_report_acceptance_fails_when_extraction_pressure_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-extraction-pressure",
        title_prefix="Phase 8.5 Extraction Pressure",
        documents=[_document_report()],
    )
    report["extractionPressure"] = {
        **report["extractionPressure"],
        "selectedTaskCount": 3,
        "selectedTaskCountByBackend": {"granite_region": 3},
        "budgetExceededCount": 0,
        "estimatedVisualTokens": 1024,
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["extractionPressure"]["status"] == "failed"
    assert summary["checks"]["extractionPressure"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-extraction-pressure",
            "invalid": [
                "selectedTaskCount",
                "selectedTaskCountByBackend",
                "budgetExceededCount",
                "estimatedVisualTokens",
            ],
            "details": report["extractionPressure"],
            "recomputed": {
                "plannedTaskCount": 3,
                "selectedTaskCount": 2,
                "selectedTaskCountByBackend": {"granite_region": 1, "qwen_semantic": 1},
                "selectedTaskCountByPage": {"1": 1, "2": 1},
                "maxTasksPerDocumentPolicy": 6,
                "maxTasksPerPagePolicy": 3,
                "budgetExceededCount": 1,
                "estimatedVisualTokens": 3072,
                "estimatedDoclingContextTokens": 768,
            },
        }
    ]


def _document_report() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-extraction-pressure",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "planner": [
            {
                "selected_task_count": 2,
                "skipped_task_count": 1,
                "abstention_count": 0,
                "missing_contract_count": 0,
                "missing_grounding_count": 0,
                "incompatible_schema_count": 0,
                "duplicate_suppressed_count": 0,
                "report_json": {
                    "maxTasksPerDocumentPolicy": 6,
                    "maxTasksPerPagePolicy": 3,
                    "estimatedDoclingContextTokens": 768,
                },
            }
        ],
        "plannerTasks": [
            {
                "id": "task-selected-granite",
                "status": "selected",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-1",
                "compatibility_mode": "exact",
                "model_output_schema_name": "granite_invoice_line_items.v1",
                "grounding_kind": "table",
                "page_number": 1,
                "task_json": {
                    "estimatedVisualTokens": 2048,
                    "grounding": {"table_id": "table-1", "page_id": "page-1"},
                },
            },
            {
                "id": "task-selected-qwen",
                "status": "selected",
                "extractor_backend": "qwen_semantic",
                "semantic_region_id": "region-2",
                "compatibility_mode": "exact",
                "model_output_schema_name": "semantic_annotation_manifest.v1",
                "grounding_kind": "page",
                "page_number": 2,
                "task_json": {
                    "estimatedVisualTokens": 1024,
                    "grounding": {"page_id": "page-2"},
                },
            },
            {
                "id": "task-skipped-budget",
                "status": "skipped_budget_exceeded",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-3",
                "compatibility_mode": "exact",
                "model_output_schema_name": "granite_payment_summary.v1",
                "page_number": 3,
                "task_json": {},
            },
        ],
    }
