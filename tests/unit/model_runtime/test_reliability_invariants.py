from __future__ import annotations

from lib.model_runtime.reliability_invariants import evaluate_hard_correctness_invariants
from lib.model_runtime.reliability_report import build_phase85_reliability_report


def test_hard_invariants_pass_for_safe_skips_and_review_required_model_rows() -> None:
    summary = evaluate_hard_correctness_invariants([_safe_document_report()])

    assert summary["status"] == "passed"
    assert summary["totalViolationCount"] == 0
    assert summary["invariants"]["selectedGraniteTasksMissingContract"]["violationCount"] == 0
    assert summary["invariants"]["modelBackedSemanticRegionAutoAccepted"]["violationCount"] == 0


def test_hard_invariants_flag_unsafe_planner_admission_and_extraction_rows() -> None:
    summary = evaluate_hard_correctness_invariants([_unsafe_document_report()])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 5
    assert summary["invariants"]["selectedGraniteTasksMissingContract"]["violationCount"] == 1
    assert summary["invariants"]["selectedGraniteTasksMissingGrounding"]["violationCount"] == 1
    assert (
        summary["invariants"]["selectedGraniteTasksIncompatibleFamilySchema"]["violationCount"] == 1
    )
    assert summary["invariants"]["admittedCandidatesWithoutConcreteEvidence"]["violationCount"] == 1
    assert summary["invariants"]["modelBackedSemanticRegionAutoAccepted"]["violationCount"] == 1


def test_hard_invariants_flag_admitted_artifacts_placeholders_and_fabrication() -> None:
    summary = evaluate_hard_correctness_invariants([_artifact_document_report()])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 5
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["violationCount"] == 1
    assert (
        summary["invariants"]["placeholderOrLiteralNullCandidatesAdmitted"]["violationCount"] == 1
    )
    assert summary["invariants"]["fabricatedCanonicalRequiredFields"]["violationCount"] == 1
    assert (
        summary["invariants"]["titleDerivedMerchantSellerWithoutAllowlist"]["violationCount"] == 1
    )
    assert summary["invariants"]["aggregateSchemasFromIncompatibleFamilies"]["violationCount"] == 1


def test_reliability_report_includes_hard_invariant_summary() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-20260604-smoke-001",
        title_prefix="Phase 8.5 Smoke",
        documents=[_unsafe_document_report()],
    )

    assert report["acceptanceGates"]["hardCorrectnessInvariants"]["status"] == "failed"
    assert (
        report["acceptanceGates"]["hardCorrectnessInvariants"]["invariants"][
            "selectedGraniteTasksMissingContract"
        ]["violationCount"]
        == 1
    )


def _safe_document_report() -> dict[str, object]:
    return {
        "document": {
            "id": "doc-safe",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "plannerTasks": [
            {
                "id": "task-selected",
                "status": "selected",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-1",
                "target_schema": "invoice",
                "canonical_target_schema": "invoice",
                "model_output_schema_name": "granite_invoice_line_items.v1",
                "compatibility_mode": "exact",
                "grounding_kind": "table",
                "page_number": 1,
                "task_json": {"grounding": {"table_id": "table-1", "page_id": "page-1"}},
            },
            {
                "id": "task-skipped",
                "status": "skipped_missing_contract",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-2",
                "target_schema": "invoice",
                "canonical_target_schema": "invoice",
                "model_output_schema_name": None,
                "compatibility_mode": "missing",
                "grounding_kind": "table",
            },
        ],
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "line_item",
                "candidate_fingerprint": "line-1",
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "description": "Labor",
                        "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                    }
                },
            }
        ],
        "extractions": [
            {
                "schema_name": "invoice",
                "extraction_scope": "semantic_region",
                "source_semantic_region_id": "region-1",
                "source_engine": "granite",
                "review_status": "needs_review",
                "is_current": True,
            }
        ],
        "fields": [],
        "lineItems": [],
        "observations": [],
    }


def _unsafe_document_report() -> dict[str, object]:
    return {
        "document": {
            "id": "doc-unsafe",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "plannerTasks": [
            {
                "id": "task-unsafe",
                "status": "selected",
                "extractor_backend": "granite_region",
                "semantic_region_id": "region-1",
                "target_schema": "invoice",
                "canonical_target_schema": "invoice",
                "model_output_schema_name": None,
                "compatibility_mode": "missing",
                "grounding_kind": None,
                "page_number": None,
                "task_json": {"grounding": {}},
            }
        ],
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "field",
                "candidate_fingerprint": "field-1",
                "evidence_concrete": False,
                "payload_json": {
                    "candidate": {
                        "field_path": "invoice.total_amount",
                        "value": "42.00",
                        "evidence": [],
                    }
                },
            }
        ],
        "extractions": [
            {
                "schema_name": "invoice",
                "extraction_scope": "semantic_region",
                "source_semantic_region_id": "region-1",
                "source_engine": "granite",
                "review_status": "auto_accepted",
                "is_current": True,
            }
        ],
        "fields": [],
        "lineItems": [],
        "observations": [],
    }


def _artifact_document_report() -> dict[str, object]:
    return {
        "document": {
            "id": "doc-artifact",
            "title": "Acme Services Invoice 1001",
            "document_family": "medical_eob",
            "review_status": "needs_review",
        },
        "plannerTasks": [],
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "field",
                "candidate_fingerprint": "artifact-1",
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "field_path": "invoice.total_amount",
                        "value": "<json_schema>",
                        "evidence": [{"page_id": "page-1"}],
                    }
                },
            },
            {
                "decision": "admitted_review_required",
                "candidate_kind": "field",
                "candidate_fingerprint": "placeholder-1",
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "field_path": "invoice.seller.display_name",
                        "value": "null",
                        "evidence": [{"page_id": "page-1"}],
                    }
                },
            },
        ],
        "extractions": [
            {
                "schema_name": "invoice",
                "extraction_scope": "document",
                "source_engine": "system_reconciler",
                "review_status": "needs_review",
                "validation_json": {"requiredFabricated": ["invoice.invoice_number"]},
                "normalization_json": {
                    "sourceFamilies": ["medical_eob"],
                    "reviewWarnings": ["aggregate_incompatible_source_family"],
                },
                "is_current": True,
            }
        ],
        "fields": [
            {
                "field_path": "invoice.invoice_number",
                "review_status": "auto_accepted",
                "value": "INV-1001",
                "evidence": [],
                "validation": {"fabricated": True},
            },
            {
                "field_path": "invoice.seller.display_name",
                "review_status": "auto_accepted",
                "value": "Acme Services",
                "evidence": [{"source": "document_title"}],
            },
        ],
        "lineItems": [],
        "observations": [],
    }
