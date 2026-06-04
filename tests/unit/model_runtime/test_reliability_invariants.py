from __future__ import annotations

from typing import Any

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.model_runtime.reliability_invariants import evaluate_hard_correctness_invariants
from lib.model_runtime.reliability_report import build_phase85_reliability_report
from lib.semantic_annotations.extraction_plan_repository import PLANNER_VERSION


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


def test_hard_invariants_treat_whitespace_granite_contract_as_missing() -> None:
    document = _safe_document_report()
    document["plannerTasks"][0]["model_output_schema_name"] = "   "
    document["plannerTasks"][0]["modelOutputSchemaName"] = "   "

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["selectedGraniteTasksMissingContract"]["violationCount"] == 1
    assert summary["invariants"]["selectedGraniteTasksMissingContract"]["examples"] == [
        {
            "reason": "missing_model_output_schema_name",
            "documentId": "task-selected",
            "entityId": "task-selected",
        }
    ]


def test_hard_invariants_treat_whitespace_grounding_values_as_missing() -> None:
    document = _safe_document_report()
    document["plannerTasks"][0]["page_number"] = "   "
    document["plannerTasks"][0]["pageNumber"] = "   "
    document["plannerTasks"][0]["task_json"] = {
        "grounding": {
            "table_id": "   ",
            "tableId": "   ",
            "page_id": "   ",
            "pageId": "   ",
        }
    }

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["selectedGraniteTasksMissingGrounding"]["violationCount"] == 1
    assert summary["invariants"]["selectedGraniteTasksMissingGrounding"]["examples"] == [
        {
            "reason": "missing_concrete_grounding",
            "documentId": "task-selected",
            "entityId": "task-selected",
        }
    ]


def test_hard_invariants_normalize_incompatible_compatibility_mode_labels() -> None:
    document = _safe_document_report()
    document["plannerTasks"][0]["compatibility_mode"] = " Incompatible Family "

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert (
        summary["invariants"]["selectedGraniteTasksIncompatibleFamilySchema"]["violationCount"] == 1
    )
    assert summary["invariants"]["selectedGraniteTasksIncompatibleFamilySchema"]["examples"] == [
        {
            "reason": "incompatible_schema_or_contract_resolution",
            "documentId": "task-selected",
            "entityId": "task-selected",
        }
    ]


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


def test_hard_invariants_flag_admitted_prompt_echo_phrases() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "admitted_review_required",
            "candidate_kind": "line_item",
            "candidate_fingerprint": "prompt-echo-line-1",
            **_admission_event_telemetry(),
            "evidence_concrete": True,
            "payload_json": {
                "candidate": {
                    "description": "Return only JSON matching the schema",
                    "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                }
            },
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["violationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["examples"] == [
        {
            "reason": "admitted_prompt_or_schema_artifact",
            "documentId": None,
            "entityId": "prompt-echo-line-1",
        }
    ]


def test_hard_invariants_normalize_admitted_event_decisions_before_quality_checks() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": " Admitted_Review_Required ",
            "candidate_kind": "line_item",
            "candidate_fingerprint": "prompt-echo-line-normalized",
            **_admission_event_telemetry(),
            "evidence_concrete": True,
            "payload_json": {
                "candidate": {
                    "description": "Return only JSON matching the schema",
                    "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                }
            },
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["violationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["examples"] == [
        {
            "reason": "admitted_prompt_or_schema_artifact",
            "documentId": None,
            "entityId": "prompt-echo-line-normalized",
        }
    ]


def test_hard_invariants_normalize_camel_case_prompt_echo_phrases() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "admitted_review_required",
            "candidate_kind": "line_item",
            "candidate_fingerprint": "prompt-echo-line-camel",
            **_admission_event_telemetry(),
            "evidence_concrete": True,
            "payload_json": {
                "candidate": {
                    "description": "ReturnOnlyJsonMatchingTheSchema",
                    "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                }
            },
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["violationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["examples"] == [
        {
            "reason": "admitted_prompt_or_schema_artifact",
            "documentId": None,
            "entityId": "prompt-echo-line-camel",
        }
    ]


def test_hard_invariants_flag_admitted_schema_artifact_keys() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "admitted_review_required",
            "candidate_kind": "field",
            "candidate_fingerprint": "schema-key-field-1",
            **_admission_event_telemetry(),
            "evidence_concrete": True,
            "payload_json": {
                "candidate": {
                    "field_path": "invoice.total_amount",
                    "value": {"$schema": "invoice.v1", "amount": "42.00"},
                    "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                }
            },
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["violationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["examples"] == [
        {
            "reason": "admitted_prompt_or_schema_artifact",
            "documentId": None,
            "entityId": "schema-key-field-1",
        }
    ]


def test_hard_invariants_normalize_camel_case_schema_artifact_keys() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "admitted_review_required",
            "candidate_kind": "field",
            "candidate_fingerprint": "schema-key-field-camel",
            **_admission_event_telemetry(),
            "evidence_concrete": True,
            "payload_json": {
                "candidate": {
                    "field_path": "invoice.total_amount",
                    "value": {
                        "responseFormat": {
                            "type": "json_object",
                        },
                    },
                    "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                }
            },
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["violationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["examples"] == [
        {
            "reason": "admitted_prompt_or_schema_artifact",
            "documentId": None,
            "entityId": "schema-key-field-camel",
        }
    ]


def test_hard_invariants_normalize_camel_case_schema_artifact_values() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "admitted_review_required",
            "candidate_kind": "field",
            "candidate_fingerprint": "schema-value-field-camel",
            **_admission_event_telemetry(),
            "evidence_concrete": True,
            "payload_json": {
                "candidate": {
                    "field_path": "invoice.total_amount",
                    "value": {
                        "format_hint": "responseFormat",
                    },
                    "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                }
            },
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["violationCount"] == 1
    assert summary["invariants"]["promptSchemaArtifactsAdmitted"]["examples"] == [
        {
            "reason": "admitted_prompt_or_schema_artifact",
            "documentId": None,
            "entityId": "schema-value-field-camel",
        }
    ]


def test_hard_invariants_flag_admitted_camel_case_placeholder_payloads() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "admitted_review_required",
            "candidate_kind": "observation",
            "candidate_fingerprint": "camel-placeholder-observation-1",
            **_admission_event_telemetry(),
            "evidence_concrete": True,
            "payload_json": {
                "candidate": {
                    "fieldName": "field",
                    "displayName": "Unknown",
                    "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                }
            },
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert (
        summary["invariants"]["placeholderOrLiteralNullCandidatesAdmitted"]["violationCount"] == 1
    )
    assert summary["invariants"]["placeholderOrLiteralNullCandidatesAdmitted"]["examples"] == [
        {
            "reason": "admitted_placeholder_or_literal_null",
            "documentId": None,
            "entityId": "camel-placeholder-observation-1",
        }
    ]


def test_hard_invariants_flag_admitted_spaced_key_placeholder_payloads() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "admitted_review_required",
            "candidate_kind": "observation",
            "candidate_fingerprint": "spaced-placeholder-observation-1",
            **_admission_event_telemetry(),
            "evidence_concrete": True,
            "payload_json": {
                "candidate": {
                    "field name": "field",
                    "display name": "Unknown",
                    "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                }
            },
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert (
        summary["invariants"]["placeholderOrLiteralNullCandidatesAdmitted"]["violationCount"] == 1
    )
    assert summary["invariants"]["placeholderOrLiteralNullCandidatesAdmitted"]["examples"] == [
        {
            "reason": "admitted_placeholder_or_literal_null",
            "documentId": None,
            "entityId": "spaced-placeholder-observation-1",
        }
    ]


def test_hard_invariants_flag_title_derived_seller_source_engine_alias() -> None:
    document = _safe_document_report()
    document["fields"].append(
        {
            "id": "field-title-seller",
            "field_path": "invoice.seller.display_name",
            "review_status": "auto_accepted",
            "value": "Acme Services",
            "evidence": [{"sourceEngine": "document_title"}],
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert (
        summary["invariants"]["titleDerivedMerchantSellerWithoutAllowlist"]["violationCount"] == 1
    )
    assert summary["invariants"]["titleDerivedMerchantSellerWithoutAllowlist"]["examples"] == [
        {
            "reason": "title_derived_merchant_seller_without_allowlist",
            "documentId": "doc-safe",
            "entityId": "field-title-seller",
        }
    ]


def test_hard_invariants_flag_title_derived_seller_row_source_engine() -> None:
    document = _safe_document_report()
    document["fields"].append(
        {
            "id": "field-title-seller-source",
            "field_path": "invoice.seller.display_name",
            "review_status": "auto_accepted",
            "source_engine": "document_title",
            "value": "Acme Services",
            "evidence": [],
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert (
        summary["invariants"]["titleDerivedMerchantSellerWithoutAllowlist"]["violationCount"] == 1
    )
    assert summary["invariants"]["titleDerivedMerchantSellerWithoutAllowlist"]["examples"] == [
        {
            "reason": "title_derived_merchant_seller_without_allowlist",
            "documentId": "doc-safe",
            "entityId": "field-title-seller-source",
        }
    ]


def test_hard_invariants_normalize_title_source_labels() -> None:
    document = _safe_document_report()
    document["canonicalFields"] = [
        {
            "id": "field-title-seller-camel-source",
            "fieldPath": " Invoice.Seller.DisplayName ",
            "reviewStatus": "accepted",
            "value": "Acme Services",
            "evidence": [{"sourceEngine": "DocumentTitle"}],
        }
    ]

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert (
        summary["invariants"]["titleDerivedMerchantSellerWithoutAllowlist"]["violationCount"] == 1
    )
    assert summary["invariants"]["titleDerivedMerchantSellerWithoutAllowlist"]["examples"] == [
        {
            "reason": "title_derived_merchant_seller_without_allowlist",
            "documentId": "doc-safe",
            "entityId": "field-title-seller-camel-source",
        }
    ]


def test_hard_invariants_flag_versioned_model_source_engine_auto_acceptance() -> None:
    for source_engine in ("granite_vision_3b", "qwen3_vl_8b"):
        document = _safe_document_report()
        document["extractions"].append(
            {
                "schema_name": "invoice",
                "extraction_scope": "semantic_region",
                "source_semantic_region_id": "region-versioned",
                "source_engine": source_engine,
                "review_status": "auto_accepted",
                "is_current": True,
            }
        )

        summary = evaluate_hard_correctness_invariants([document])

        assert summary["status"] == "failed"
        assert summary["totalViolationCount"] == 1
        assert summary["invariants"]["modelBackedSemanticRegionAutoAccepted"]["violationCount"] == 1
        assert summary["invariants"]["modelBackedSemanticRegionAutoAccepted"]["examples"] == [
            {
                "reason": "model_backed_semantic_region_auto_accepted",
                "documentId": None,
                "entityId": None,
            }
        ]


def test_hard_invariants_normalize_model_extraction_scope_and_review_status() -> None:
    document = _safe_document_report()
    document["semanticRegionExtractions"] = [
        {
            "schemaName": "invoice",
            "extractionScope": " Semantic_Region ",
            "sourceSemanticRegionId": "region-normalized",
            "sourceEngine": " Granite_Vision_3B ",
            "reviewStatus": " Auto_Accepted ",
        }
    ]

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["modelBackedSemanticRegionAutoAccepted"]["violationCount"] == 1
    assert summary["invariants"]["modelBackedSemanticRegionAutoAccepted"]["examples"] == [
        {
            "reason": "model_backed_semantic_region_auto_accepted",
            "documentId": None,
            "entityId": None,
        }
    ]


def test_hard_invariants_flag_rejected_candidate_rows_inserted() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "rejected_missing_evidence",
            "candidate_kind": "field",
            "candidate_fingerprint": "rejected-field-fingerprint",
            **_admission_event_telemetry(),
            "field_path": "invoice.total_amount",
            "payload_json": {
                "field_path": "invoice.total_amount",
                "value": "42.00",
            },
        }
    )
    document["fields"].append(
        {
            "id": "field-rejected",
            "candidate_fingerprint": "rejected-field-fingerprint",
            "field_path": "invoice.total_amount",
            "value": "42.00",
            "status": "proposed",
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["rejectedCandidatesInserted"]["violationCount"] == 1
    assert summary["invariants"]["rejectedCandidatesInserted"]["examples"] == [
        {
            "reason": "rejected_candidate_inserted",
            "documentId": "doc-safe",
            "entityId": "field-rejected",
        }
    ]


def test_hard_invariants_flag_rejected_candidate_canonical_alias_rows_inserted() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "rejected_missing_evidence",
            "candidate_kind": "field",
            "candidate_fingerprint": "rejected-canonical-field",
            **_admission_event_telemetry(),
            "field_path": "invoice.total_amount",
            "payload_json": {
                "field_path": "invoice.total_amount",
                "value": "42.00",
            },
        }
    )
    document["canonicalFields"] = [
        {
            "id": "canonical-field-rejected",
            "candidateFingerprint": "rejected-canonical-field",
            "fieldPath": "invoice.total_amount",
            "value": "42.00",
            "reviewStatus": "needs_review",
        }
    ]

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["rejectedCandidatesInserted"]["violationCount"] == 1
    assert summary["invariants"]["rejectedCandidatesInserted"]["examples"] == [
        {
            "reason": "rejected_candidate_inserted",
            "documentId": "doc-safe",
            "entityId": "canonical-field-rejected",
        }
    ]


def test_hard_invariants_normalize_rejected_event_decisions_before_matching_rows() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": " Rejected_Missing_Evidence ",
            "candidateKind": "observation",
            "candidateFingerprint": "rejected-observation-fingerprint",
            **_admission_event_telemetry(),
            "fieldPath": "service.note",
            "payloadJson": {
                "candidate": {
                    "observationFamily": "service_record",
                    "fieldName": "service.note",
                    "valueJson": {"text": "Deferred rear tire service"},
                },
            },
        }
    )
    document["observationCandidates"] = [
        {
            "id": "observation-rejected",
            "observationFamily": "service_record",
            "fieldName": "service.note",
            "valueJson": {"text": "Deferred rear tire service"},
            "status": "needs_review",
        }
    ]

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["rejectedCandidatesInserted"]["violationCount"] == 1
    assert summary["invariants"]["rejectedCandidatesInserted"]["examples"] == [
        {
            "reason": "rejected_candidate_inserted",
            "documentId": "doc-safe",
            "entityId": "observation-rejected",
        }
    ]


def test_hard_invariants_normalize_rejected_event_candidate_kind_before_matching_rows() -> None:
    document = _safe_document_report()
    document["admissionEvents"].append(
        {
            "decision": "rejected_missing_evidence",
            "candidateKind": " Line_Item ",
            "candidateFingerprint": "rejected-line-kind-fingerprint",
            **_admission_event_telemetry(),
            "payloadJson": {
                "candidate": {
                    "description": "Front tire service",
                    "code": "TIRE",
                    "netAmount": "145.00",
                    "grossAmount": "145.00",
                },
            },
        }
    )
    document["lineItemCandidates"] = [
        {
            "id": "line-item-rejected-kind",
            "description": "Front tire service",
            "code": "TIRE",
            "netAmount": "145.00",
            "grossAmount": "145.00",
            "status": "needs_review",
        }
    ]

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["rejectedCandidatesInserted"]["violationCount"] == 1
    assert summary["invariants"]["rejectedCandidatesInserted"]["examples"] == [
        {
            "reason": "rejected_candidate_inserted",
            "documentId": "doc-safe",
            "entityId": "line-item-rejected-kind",
        }
    ]


def test_hard_invariants_flag_fabricated_canonical_field_alias_rows() -> None:
    document = _safe_document_report()
    document["canonicalFields"] = [
        {
            "id": "canonical-field-fabricated",
            "fieldPath": "invoice.invoice_number",
            "reviewStatus": "auto_accepted",
            "value": "INV-1001",
            "evidence": [],
            "validation": {"fabricated": True},
        }
    ]

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["fabricatedCanonicalRequiredFields"]["violationCount"] == 1
    assert summary["invariants"]["fabricatedCanonicalRequiredFields"]["examples"] == [
        {
            "reason": "fabricated_required_field",
            "documentId": "doc-safe",
            "entityId": "canonical-field-fabricated",
        }
    ]


def test_hard_invariants_normalize_required_field_paths_before_fabrication_check() -> None:
    document = _safe_document_report()
    document["canonicalFields"] = [
        {
            "id": "canonical-field-camel-path-fabricated",
            "fieldPath": " Invoice.InvoiceNumber ",
            "reviewStatus": "accepted",
            "value": "INV-1001",
            "evidence": [],
        }
    ]

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["fabricatedCanonicalRequiredFields"]["violationCount"] == 1
    assert summary["invariants"]["fabricatedCanonicalRequiredFields"]["examples"] == [
        {
            "reason": "fabricated_required_field",
            "documentId": "doc-safe",
            "entityId": "canonical-field-camel-path-fabricated",
        }
    ]


def test_hard_invariants_normalize_aggregate_schema_and_source_families() -> None:
    document = _safe_document_report()
    document["extractions"].append(
        {
            "id": "aggregate-compatible-cased",
            "schemaName": " Invoice ",
            "extractionScope": " Aggregate ",
            "sourceEngine": "system_reconciler",
            "reviewStatus": "needs_review",
            "normalizationJson": {"sourceFamilies": [" invoice "]},
        }
    )

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "passed"
    assert summary["totalViolationCount"] == 0
    assert summary["invariants"]["aggregateSchemasFromIncompatibleFamilies"]["violationCount"] == 0


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


def _safe_document_report() -> dict[str, Any]:
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
                **_admission_event_telemetry(),
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


def _unsafe_document_report() -> dict[str, Any]:
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
                **_admission_event_telemetry(),
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


def _artifact_document_report() -> dict[str, Any]:
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
                **_admission_event_telemetry(),
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
                **_admission_event_telemetry(),
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


def _admission_event_telemetry() -> dict[str, str]:
    return {
        "run_id": "phase85-20260604-smoke-001",
        "planner_version": PLANNER_VERSION,
        "candidate_gate_version": CANDIDATE_GATE_VERSION,
        "contract_registry_version": CONTRACT_REGISTRY_VERSION,
    }
