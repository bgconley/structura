from __future__ import annotations

from lib.documents.analysis_intake import (
    build_phase9_document_intake,
    phase9_document_eligibility,
    phase9_mutation_violations,
)


def test_phase9_intake_disables_analysis_for_admitted_placeholder_artifacts() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-artifact-admitted",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [_concrete_evidence()],
                }
            ],
            "admissionEvents": [
                {
                    "decision": "admitted_review_required",
                    "reasons": ["placeholder_or_null_value"],
                },
                {
                    "decision": "admitted_review_required",
                    "reasons": ["fake_schema_line_item"],
                },
                {
                    "decision": "rejected_placeholder",
                    "reasons": ["placeholder_or_null_value"],
                },
            ],
        }
    )

    assert intake["documentQuality"]["has_admitted_artifact"] is True
    assert intake["eligibility"] == "analysis_disabled_artifact_regression"


def test_phase9_document_eligibility_states() -> None:
    assert (
        phase9_document_eligibility(
            {
                "operational_status": "pipeline_failed",
                "canonical_fact_count": 1,
                "candidate_count": 1,
                "evidence_locator_coverage": 1.0,
                "has_admitted_artifact": False,
            }
        )
        == "analysis_disabled_operational_failure"
    )
    assert (
        phase9_document_eligibility(
            {
                "operational_status": "completed",
                "canonical_fact_count": 0,
                "candidate_count": 0,
                "evidence_locator_coverage": 1.0,
                "has_admitted_artifact": False,
            }
        )
        == "analysis_limited_no_extracted_facts"
    )
    assert (
        phase9_document_eligibility(
            {
                "operational_status": "completed",
                "canonical_fact_count": 2,
                "candidate_count": 1,
                "evidence_locator_coverage": 0.79,
                "has_admitted_artifact": False,
            }
        )
        == "analysis_review_only_evidence_sparse"
    )
    assert (
        phase9_document_eligibility(
            {
                "operational_status": "completed",
                "canonical_fact_count": 2,
                "candidate_count": 1,
                "evidence_locator_coverage": 0.95,
                "has_admitted_artifact": True,
            }
        )
        == "analysis_disabled_artifact_regression"
    )
    assert (
        phase9_document_eligibility(
            {
                "operational_status": "completed",
                "canonical_fact_count": 2,
                "candidate_count": 1,
                "evidence_locator_coverage": 0.95,
                "has_admitted_artifact": False,
            }
        )
        == "analysis_enabled_with_uncertainty"
    )


def test_phase9_intake_disables_analysis_for_target_queue_dead_letter_jobs() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-dead-letter",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [{"semanticRegionId": "region-1", "pageNumber": 1}],
                }
            ],
            "jobs": [
                {
                    "queueName": "extraction",
                    "jobType": "extract",
                    "status": "dead_letter",
                }
            ],
        }
    )

    assert intake["documentQuality"]["operational_status"] == "pipeline_failed"
    assert intake["eligibility"] == "analysis_disabled_operational_failure"


def test_phase9_intake_treats_retryable_failed_jobs_as_in_progress() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-retry-pending",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [{"semanticRegionId": "region-1", "pageNumber": 1}],
                }
            ],
            "jobs": [
                {
                    "queueName": "extraction",
                    "jobType": "extract",
                    "status": "failed",
                    "attemptCount": 1,
                    "maxAttempts": 5,
                    "errorJson": {"retryable": True},
                }
            ],
        }
    )

    assert intake["documentQuality"]["operational_status"] == "completed"
    assert intake["eligibility"] == "analysis_enabled_with_uncertainty"


def test_phase9_intake_disables_analysis_for_exhausted_failed_jobs() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-attempts-exhausted",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [{"semanticRegionId": "region-1", "pageNumber": 1}],
                }
            ],
            "jobs": [
                {
                    "queueName": "extraction",
                    "jobType": "extract",
                    "status": "failed",
                    "attemptCount": 5,
                    "maxAttempts": 5,
                }
            ],
        }
    )

    assert intake["documentQuality"]["operational_status"] == "pipeline_failed"
    assert intake["eligibility"] == "analysis_disabled_operational_failure"


def test_phase9_intake_disables_analysis_for_nonretryable_failed_jobs() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-nonretryable-failure",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [{"semanticRegionId": "region-1", "pageNumber": 1}],
                }
            ],
            "jobs": [
                {
                    "queueName": "extraction",
                    "jobType": "extract",
                    "status": "failed",
                    "errorJson": {"retryable": False},
                }
            ],
        }
    )

    assert intake["documentQuality"]["operational_status"] == "pipeline_failed"
    assert intake["eligibility"] == "analysis_disabled_operational_failure"


def test_phase9_intake_keeps_quality_outcomes_distinct_from_operational_failure() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-quality-review",
            "documentQuality": {"operationalStatus": "needs_human_review"},
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [{"semanticRegionId": "region-1", "pageNumber": 1}],
                }
            ],
        }
    )

    assert intake["documentQuality"]["quality_outcome"] == "needs_human_review"
    assert intake["documentQuality"]["operational_status"] == "completed"
    assert intake["eligibility"] == "analysis_enabled_with_uncertainty"


def test_phase9_intake_requires_structura_owned_evidence_locator() -> None:
    source_text_only = build_phase9_document_intake(
        {
            "id": "doc-source-text-only",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [
                        {
                            "sourceText": "Invoice total $42.50",
                        }
                    ],
                }
            ],
        }
    )

    assert source_text_only["documentQuality"]["evidence_locator_coverage"] == 0.0
    assert source_text_only["eligibility"] == "analysis_review_only_evidence_sparse"

    semantic_region_anchored = build_phase9_document_intake(
        {
            "id": "doc-semantic-region-anchored",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [
                        {
                            "semanticRegionId": "region-1",
                            "pageNumber": 1,
                            "sourceText": "Invoice total $42.50",
                        }
                    ],
                }
            ],
        }
    )

    assert semantic_region_anchored["documentQuality"]["evidence_locator_coverage"] == 1.0
    assert semantic_region_anchored["eligibility"] == "analysis_enabled_with_uncertainty"


def test_phase9_intake_requires_page_context_for_structural_locators() -> None:
    bbox_without_page = build_phase9_document_intake(
        {
            "id": "doc-bbox-without-page",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [{"bbox": [1, 2, 3, 4], "sourceEngine": "granite_vision_3b"}],
                }
            ],
        }
    )

    assert bbox_without_page["documentQuality"]["evidence_locator_coverage"] == 0.0
    assert bbox_without_page["eligibility"] == "analysis_review_only_evidence_sparse"

    table_without_row = build_phase9_document_intake(
        {
            "id": "doc-table-without-row",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [
                        {
                            "tableId": "table-1",
                            "pageNumber": 1,
                            "sourceEngine": "granite_vision_3b",
                        }
                    ],
                }
            ],
        }
    )

    assert table_without_row["documentQuality"]["evidence_locator_coverage"] == 0.0
    assert table_without_row["eligibility"] == "analysis_review_only_evidence_sparse"

    element_with_page = build_phase9_document_intake(
        {
            "id": "doc-element-with-page",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [
                        {
                            "elementId": "element-1",
                            "pageNumber": 1,
                            "sourceEngine": "granite_vision_3b",
                        }
                    ],
                }
            ],
        }
    )

    assert element_with_page["documentQuality"]["evidence_locator_coverage"] == 1.0
    assert element_with_page["eligibility"] == "analysis_enabled_with_uncertainty"


def test_phase9_output_mutation_guard_blocks_state_changes() -> None:
    violations = phase9_mutation_violations(
        {
            "answer": "This invoice looks unpaid.",
            "canonicalFields": [{"fieldPath": "invoice.total_amount"}],
            "relationships": [{"relationshipType": "invoice_for"}],
            "tags": ["tax"],
            "tagIds": ["tag-1"],
            "reviewStatus": "auto_accepted",
        }
    )

    assert violations == [
        "canonicalFields",
        "relationships",
        "tags",
        "tagIds",
        "reviewStatus",
    ]


def test_phase9_output_mutation_guard_blocks_snake_case_state_changes() -> None:
    violations = phase9_mutation_violations(
        {
            "answer": "Draft only.",
            "canonical_fields": [{"field_path": "invoice.total_amount"}],
            "document_relationships": [{"relationship_type": "invoice_for"}],
            "folder_ids": ["folder-1"],
            "primary_folder_id": "folder-1",
            "tag_ids": ["tag-1"],
            "document_deadlines": [{"due_on": "2026-06-01"}],
            "review_tasks": [{"id": "task-1"}],
            "review_status": "auto_accepted",
        }
    )

    assert violations == [
        "canonical_fields",
        "document_relationships",
        "folder_ids",
        "primary_folder_id",
        "tag_ids",
        "document_deadlines",
        "review_tasks",
        "review_status",
    ]


def _evidence() -> dict[str, object]:
    return {
        "pageNumber": 1,
        "sourceEngine": "granite_vision_3b",
        "sourceText": "Invoice total $42.50",
    }


def _concrete_evidence() -> dict[str, object]:
    return {
        **_evidence(),
        "elementId": "element-1",
    }
