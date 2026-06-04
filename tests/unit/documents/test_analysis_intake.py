from __future__ import annotations

import json

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


def test_phase9_intake_excludes_debug_envelopes_from_truth_context() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-1",
            "fields": [],
            "lineItems": [],
            "semanticRegionExtractions": [
                {
                    "id": "extraction-1",
                    "promptVersion": "phase8_5-granite-structured-v1",
                    "normalized": {
                        "invoice": {
                            "total_amount": {
                                "amount": 42.5,
                                "source": "debug-only-normalized-payload",
                            }
                        }
                    },
                    "normalization": {
                        "regionEnvelope": {
                            "facts": [{"field_path": "invoice.total_amount"}],
                            "repairs": ["wrapped_data_invoice_line_items"],
                        }
                    },
                    "metadata": {
                        "visualInputPlan": {"route": "full_page"},
                        "adapterTrace": {"finish_reason": "stop"},
                        "rawModelOutput": {"text": "debug raw model output"},
                    },
                }
            ],
        }
    )

    truth_json = json.dumps(intake["truth"], sort_keys=True)
    assert "debug-only-normalized-payload" not in truth_json
    assert "regionEnvelope" not in truth_json
    assert "raw model output" not in truth_json
    assert intake["debug"]["excludedFromTruth"] is True
    assert set(intake["debug"]["availableSurfaces"]) >= {
        "prompt_versions",
        "visual_plan_internals",
        "region_envelope",
        "normalization_repairs",
        "adapter_traces",
        "raw_model_output",
    }


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


def test_phase9_output_mutation_guard_blocks_state_changes() -> None:
    violations = phase9_mutation_violations(
        {
            "answer": "This invoice looks unpaid.",
            "canonicalFields": [{"fieldPath": "invoice.total_amount"}],
            "relationships": [{"relationshipType": "invoice_for"}],
            "tags": ["tax"],
            "reviewStatus": "auto_accepted",
        }
    )

    assert violations == [
        "canonicalFields",
        "relationships",
        "tags",
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
