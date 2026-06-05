from __future__ import annotations

from copy import deepcopy
from typing import Any

from lib.model_runtime.reliability_fingerprints import repeatability_fingerprints


def test_repeatability_fingerprints_ignore_report_row_order() -> None:
    documents = [_document("doc-1"), _document("doc-2")]
    reordered = [deepcopy(documents[1]), deepcopy(documents[0])]
    for document in reordered:
        for key in ("semanticRegions", "plannerTasks", "fields", "lineItems", "reviewTasks"):
            document[key] = list(reversed(document[key]))

    first = repeatability_fingerprints(documents, {"rejectionReasons": {"duplicate": 1}})
    second = repeatability_fingerprints(reordered, {"rejectionReasons": {"duplicate": 1}})

    assert first == second


def test_repeatability_fingerprints_ignore_relationship_suggestions() -> None:
    first_document = _document("doc-1")
    second_document = deepcopy(first_document)
    first_document["reviewTasks"].append(
        {
            "task_type": "relationship_suggestion",
            "status": "open",
            "reason": "Exact content fingerprint match.",
            "priority": 75,
        }
    )
    second_document["reviewTasks"].extend(
        [
            {
                "task_type": "relationship_suggestion",
                "status": "open",
                "reason": "Exact content fingerprint match.",
                "priority": 75,
            },
            {
                "task_type": "relationship_suggestion",
                "status": "open",
                "reason": "Exact content fingerprint match.",
                "priority": 75,
            },
        ]
    )

    first = repeatability_fingerprints([first_document], {"rejectionReasons": {}})
    second = repeatability_fingerprints([second_document], {"rejectionReasons": {}})

    assert first["reviewTasks"] == second["reviewTasks"]


def _document(document_id: str) -> dict[str, Any]:
    suffix = document_id[-1]
    return {
        "document": {
            "id": document_id,
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "semanticRegions": [
            {
                "semantic_region_id": f"region-{suffix}-a",
                "page_number": 1,
                "semantic_type": "invoice_line_item_table",
                "granite_task": "tables_json",
                "target_schema": "invoice",
                "grounding_kind": "table",
                "review_required": True,
            },
            {
                "semantic_region_id": f"region-{suffix}-b",
                "page_number": 2,
                "semantic_type": "payment_summary",
                "granite_task": "kvp",
                "target_schema": "invoice",
                "grounding_kind": "region",
                "review_required": True,
            },
        ],
        "plannerTasks": [
            {
                "id": f"task-{suffix}-a",
                "status": "selected",
                "semantic_type": "invoice_line_item_table",
                "extractor_backend": "granite_region",
                "target_schema": "invoice",
                "canonical_target_schema": "invoice",
                "model_output_schema_name": "granite_invoice_line_items.v1",
                "compatibility_mode": "exact",
                "page_number": 1,
            },
            {
                "id": f"task-{suffix}-b",
                "status": "skipped_budget_exceeded",
                "semantic_type": "payment_summary",
                "extractor_backend": "granite_region",
                "target_schema": "invoice",
                "canonical_target_schema": "invoice",
                "model_output_schema_name": "granite_payment_summary.v1",
                "compatibility_mode": "exact",
                "page_number": 2,
            },
        ],
        "admissionEvents": [
            {"candidate_fingerprint": f"candidate-{suffix}-b"},
            {"candidate_fingerprint": f"candidate-{suffix}-a"},
        ],
        "fields": [
            {"field_path": "invoice.total_amount", "value": "10.00", "status": "needs_review"},
            {
                "field_path": "invoice.invoice_number",
                "value": f"INV-{suffix}",
                "status": "needs_review",
            },
        ],
        "lineItems": [
            {"description": "Labor", "net_amount": "7.00", "status": "needs_review"},
            {"description": "Parts", "net_amount": "3.00", "status": "needs_review"},
        ],
        "observations": [],
        "reviewTasks": [
            {"id": f"review-{suffix}-b", "task_type": "candidate", "status": "open"},
            {"id": f"review-{suffix}-a", "task_type": "quality", "status": "open"},
        ],
    }
