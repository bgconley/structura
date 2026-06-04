from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_report_acceptance_fails_when_planner_summary_lineage_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-planner-summary",
        title_prefix="Phase 8.5 Planner Summary",
        documents=[_document_report()],
    )
    report["plannerSummary"] = {
        **report["plannerSummary"],
        "runId": "phase85-other-run",
        "plannerVersion": "phase8_5-old-planner",
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["plannerSummary"]["status"] == "failed"
    assert summary["checks"]["plannerSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-planner-summary",
            "invalid": ["runId", "plannerVersion"],
            "details": report["plannerSummary"],
            "recomputed": {
                "runId": "phase85-planner-summary",
                "plannerVersion": report["runManifest"]["planner_version"],
                "selectedTaskCount": 1,
                "skippedTaskCount": 1,
                "abstentionCount": 0,
                "missingContractCount": 1,
                "missingGroundingCount": 0,
                "incompatibleSchemaCount": 0,
                "duplicateSuppressedCount": 0,
                "contractResolutionModes": {"exact": 1, "missing": 1},
            },
        }
    ]


def test_report_acceptance_fails_when_planner_summary_is_stale() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-planner-summary",
        title_prefix="Phase 8.5 Planner Summary",
        documents=[_document_report()],
    )
    report["plannerSummary"] = {
        **report["plannerSummary"],
        "selectedTaskCount": 2,
        "skippedTaskCount": 0,
        "missingContractCount": 0,
        "contractResolutionModes": {"exact": 2},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["plannerSummary"]["status"] == "failed"
    assert summary["checks"]["plannerSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-planner-summary",
            "invalid": [
                "selectedTaskCount",
                "skippedTaskCount",
                "missingContractCount",
                "contractResolutionModes",
            ],
            "details": report["plannerSummary"],
            "recomputed": {
                "runId": "phase85-planner-summary",
                "plannerVersion": report["runManifest"]["planner_version"],
                "selectedTaskCount": 1,
                "skippedTaskCount": 1,
                "abstentionCount": 0,
                "missingContractCount": 1,
                "missingGroundingCount": 0,
                "incompatibleSchemaCount": 0,
                "duplicateSuppressedCount": 0,
                "contractResolutionModes": {"exact": 1, "missing": 1},
            },
        }
    ]


def test_report_planner_summary_normalizes_contract_resolution_modes() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-planner-summary",
        title_prefix="Phase 8.5 Planner Summary",
        documents=[_document_report_with_cased_contract_modes()],
    )

    assert report["plannerSummary"]["contractResolutionModes"] == {
        "exact": 1,
        "missing": 1,
    }

    report["plannerSummary"] = {
        **report["plannerSummary"],
        "contractResolutionModes": {" Exact ": 1, " Missing ": 1},
    }

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["plannerSummary"]["status"] == "failed"
    assert summary["checks"]["plannerSummary"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-planner-summary",
            "invalid": ["contractResolutionModes"],
            "details": report["plannerSummary"],
            "recomputed": {
                "runId": "phase85-planner-summary",
                "plannerVersion": report["runManifest"]["planner_version"],
                "selectedTaskCount": 1,
                "skippedTaskCount": 1,
                "abstentionCount": 0,
                "missingContractCount": 1,
                "missingGroundingCount": 0,
                "incompatibleSchemaCount": 0,
                "duplicateSuppressedCount": 0,
                "contractResolutionModes": {"exact": 1, "missing": 1},
            },
        }
    ]


def _document_report() -> dict[str, Any]:
    return {
        "document": {
            "id": "doc-planner-summary",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "planner": [
            {
                "selected_task_count": 1,
                "skipped_task_count": 1,
                "abstention_count": 0,
                "missing_contract_count": 1,
                "missing_grounding_count": 0,
                "incompatible_schema_count": 0,
                "duplicate_suppressed_count": 0,
            }
        ],
        "plannerTasks": [
            {
                "id": "task-selected",
                "status": "selected",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-1",
                "compatibility_mode": "exact",
                "model_output_schema_name": "granite_invoice_line_items.v1",
                "grounding_kind": "table",
                "page_number": 1,
                "task_json": {"grounding": {"table_id": "table-1", "page_id": "page-1"}},
            },
            {
                "id": "task-skipped",
                "status": "skipped_missing_contract",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-2",
                "compatibility_mode": "missing",
                "model_output_schema_name": None,
            },
        ],
    }


def _document_report_with_cased_contract_modes() -> dict[str, Any]:
    document = _document_report()
    document["plannerTasks"][0]["compatibility_mode"] = " Exact "
    document["plannerTasks"][1]["compatibility_mode"] = " Missing "
    return document
