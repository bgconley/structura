from __future__ import annotations

import json

from lib.documents.analysis_intake import (
    build_phase9_document_intake,
    phase9_document_eligibility,
    phase9_mutation_violations,
)


def test_phase9_intake_labels_review_required_candidates_as_uncertain() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-1",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [_evidence()],
                }
            ],
            "fieldCandidates": [
                {
                    "fieldPath": "invoice.seller.display_name",
                    "value": "Acme Services",
                    "status": "needs_review",
                    "evidence": [_evidence()],
                }
            ],
            "lineItemCandidates": [
                {
                    "description": "Labor",
                    "status": "needs_review",
                    "evidence": [_evidence()],
                }
            ],
            "observations": [
                {
                    "observationFamily": "invoice",
                    "fieldName": "ambiguous_note",
                    "status": "needs_review",
                    "value": {"text": "Possible late fee"},
                    "evidence": [_evidence()],
                }
            ],
        }
    )

    assert intake["truth"]["canonicalFields"][0]["fieldPath"] == "invoice.total_amount"
    review_items = (
        intake["review"]["fieldCandidates"]
        + intake["review"]["lineItemCandidates"]
        + intake["review"]["observationCandidates"]
    )
    assert len(review_items) == 3
    assert {item["surface"] for item in review_items} == {"review"}
    assert {item["uncertaintyLabel"] for item in review_items} == {"uncertain_review_required"}


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


def _evidence() -> dict[str, object]:
    return {
        "pageNumber": 1,
        "sourceEngine": "granite_vision_3b",
        "sourceText": "Invoice total $42.50",
    }
