from __future__ import annotations

from typing import Any

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.region_envelope import REGION_ENVELOPE_VERSION
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)
from lib.model_runtime.reliability_acceptance import evaluate_phase85_report_acceptance
from lib.model_runtime.reliability_invariants import evaluate_hard_correctness_invariants


def test_hard_invariants_flag_missing_admission_event_run_lineage() -> None:
    summary = evaluate_hard_correctness_invariants([_document_missing_run_lineage()])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 2
    assert summary["invariants"]["admissionEventsMissingTelemetry"] == {
        "description": (
            "Admission events must include queryable lineage, gate versions, "
            "and candidate fingerprints."
        ),
        "violationCount": 2,
        "examples": [
            {
                "reason": "missing_run_id",
                "documentId": None,
                "entityId": "line-fingerprint-1",
            },
            {
                "reason": "missing_planner_version",
                "documentId": None,
                "entityId": "line-fingerprint-1",
            },
        ],
    }


def test_hard_invariants_flag_missing_admission_event_telemetry() -> None:
    summary = evaluate_hard_correctness_invariants([_document_with_missing_telemetry()])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 6
    assert summary["invariants"]["admissionEventsMissingTelemetry"] == {
        "description": (
            "Admission events must include queryable lineage, gate versions, "
            "and candidate fingerprints."
        ),
        "violationCount": 6,
        "examples": _missing_telemetry_examples(),
    }


def test_hard_invariants_require_region_envelope_for_versioned_model_sources() -> None:
    document = _document_with_versioned_model_source_missing_region_envelope()

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["admissionEventsMissingTelemetry"] == {
        "description": (
            "Admission events must include queryable lineage, gate versions, "
            "and candidate fingerprints."
        ),
        "violationCount": 1,
        "examples": [
            {
                "reason": "missing_region_envelope_version",
                "documentId": None,
                "entityId": "line-fingerprint-versioned",
            }
        ],
    }


def test_hard_invariants_require_semantic_plan_lineage_for_model_sources() -> None:
    document = _document_with_versioned_model_source_missing_semantic_plan_lineage()

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 3
    assert summary["invariants"]["admissionEventsMissingTelemetry"] == {
        "description": (
            "Admission events must include queryable lineage, gate versions, "
            "and candidate fingerprints."
        ),
        "violationCount": 3,
        "examples": [
            {
                "reason": "missing_plan_id",
                "documentId": None,
                "entityId": "line-fingerprint-planless",
            },
            {
                "reason": "missing_plan_task_id",
                "documentId": None,
                "entityId": "line-fingerprint-planless",
            },
            {
                "reason": "missing_semantic_annotation_id",
                "documentId": None,
                "entityId": "line-fingerprint-planless",
            },
        ],
    }


def test_hard_invariants_normalize_placeholder_values_before_admission_check() -> None:
    document = _document_with_spaced_placeholder_value()

    summary = evaluate_hard_correctness_invariants([document])

    assert summary["status"] == "failed"
    assert summary["totalViolationCount"] == 1
    assert summary["invariants"]["placeholderOrLiteralNullCandidatesAdmitted"] == {
        "description": "Placeholder and literal-null candidate values must never be admitted.",
        "violationCount": 1,
        "examples": [
            {
                "reason": "admitted_placeholder_or_literal_null",
                "documentId": None,
                "entityId": "placeholder-value-spaced",
            }
        ],
    }


def test_report_acceptance_fails_when_admission_event_telemetry_is_missing() -> None:
    report = _passing_report_with_documents([_document_with_missing_telemetry()])

    summary = evaluate_phase85_report_acceptance([report])

    assert summary["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["status"] == "failed"
    assert summary["checks"]["hardCorrectnessInvariants"]["failures"] == [
        {
            "reportIndex": 0,
            "runId": "phase85-pass-1",
            "status": "passed",
            "details": report["acceptanceGates"]["hardCorrectnessInvariants"],
            "invalid": ["recomputed.totalViolationCount"],
            "recomputed": {
                "status": "failed",
                "totalViolationCount": 6,
                "invariants": {
                    "admissionEventsMissingTelemetry": {
                        "description": (
                            "Admission events must include queryable lineage, "
                            "gate versions, and candidate fingerprints."
                        ),
                        "violationCount": 6,
                        "examples": _missing_telemetry_examples(),
                    }
                },
            },
        }
    ]


def _document_missing_run_lineage() -> dict[str, Any]:
    return {
        "document": {"id": "doc-missing-run-lineage", "document_family": "invoice"},
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "line_item",
                "candidate_fingerprint": "line-fingerprint-1",
                "candidate_gate_version": CANDIDATE_GATE_VERSION,
                "contract_registry_version": CONTRACT_REGISTRY_VERSION,
                "region_envelope_version": REGION_ENVELOPE_VERSION,
                **_semantic_plan_lineage(),
                "source_engine": "granite",
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "description": "Labor",
                        "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                    }
                },
            }
        ],
    }


def _document_with_versioned_model_source_missing_region_envelope() -> dict[str, Any]:
    return {
        "document": {"id": "doc-versioned-model-source", "document_family": "invoice"},
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "line_item",
                "candidate_fingerprint": "line-fingerprint-versioned",
                "run_id": "phase85-smoke-versioned",
                "planner_version": "planner-v1",
                "candidate_gate_version": CANDIDATE_GATE_VERSION,
                "contract_registry_version": CONTRACT_REGISTRY_VERSION,
                **_semantic_plan_lineage(),
                "source_engine": "granite_vision_3b",
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "description": "Labor",
                        "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                    }
                },
            }
        ],
    }


def _document_with_versioned_model_source_missing_semantic_plan_lineage() -> dict[str, Any]:
    return {
        "document": {"id": "doc-versioned-planless", "document_family": "invoice"},
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "line_item",
                "candidate_fingerprint": "line-fingerprint-planless",
                "run_id": "phase85-smoke-planless",
                "planner_version": "planner-v1",
                "candidate_gate_version": CANDIDATE_GATE_VERSION,
                "contract_registry_version": CONTRACT_REGISTRY_VERSION,
                "region_envelope_version": REGION_ENVELOPE_VERSION,
                "semantic_region_id": "region-1",
                "source_engine": "granite_vision_3b",
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "description": "Labor",
                        "evidence": [{"page_id": "page-1", "semantic_region_id": "region-1"}],
                    }
                },
            }
        ],
    }


def _document_with_missing_telemetry() -> dict[str, Any]:
    return {
        "document": {"id": "doc-missing-telemetry", "document_family": "invoice"},
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "field",
                "candidate_fingerprint": "",
                "candidate_gate_version": "",
                "contract_registry_version": "",
                "region_envelope_version": "",
                "field_path": "invoice.total_amount",
                **_semantic_plan_lineage(),
                "source_engine": "granite",
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "field_path": "invoice.total_amount",
                        "value": "42.00",
                        "evidence": [{"page_id": "page-1"}],
                    }
                },
            }
        ],
    }


def _document_with_spaced_placeholder_value() -> dict[str, Any]:
    return {
        "document": {"id": "doc-spaced-placeholder", "document_family": "invoice"},
        "admissionEvents": [
            {
                "decision": "admitted_review_required",
                "candidate_kind": "field",
                "candidate_fingerprint": "placeholder-value-spaced",
                "run_id": "phase85-smoke-placeholder",
                "planner_version": "planner-v1",
                "candidate_gate_version": CANDIDATE_GATE_VERSION,
                "contract_registry_version": CONTRACT_REGISTRY_VERSION,
                "evidence_concrete": True,
                "payload_json": {
                    "candidate": {
                        "field_path": "invoice.notes",
                        "value": "Visible Field",
                        "evidence": [{"page_id": "page-1"}],
                    }
                },
            }
        ],
    }


def _passing_report_with_documents(documents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "runId": "phase85-pass-1",
        "fixtureType": "model_backed",
        "measuredAt": "2026-06-04T12:00:00+00:00",
        "runManifest": {
            "run_id": "phase85-pass-1",
            "pipeline_version": "phase8_5_reliability_v1",
            "model_mode": "live",
            "semantic_profile": QWEN_SEMANTIC_PROFILE,
            "granite_profile": GRANITE_VISION_PROFILE,
            "text_embedding_profile": TEXT_EMBED_PROFILE,
            "visual_embedding_profile": VISUAL_EMBED_PROFILE,
        },
        "documents": documents,
        "plannerSummary": {"selectedTaskCount": 2},
        "candidateAdmissionSummary": {"admittedCount": 2, "rejectedCount": 0},
        "contractSummary": {"contractedTaskCount": 2, "missingContractTaskCount": 0},
        "evidenceSummary": {"concreteEvidenceCoverage": 1.0},
        "dedupeSummary": {"totalDuplicateSuppressionCount": 0},
        "envelopeSummary": {"concreteEvidenceCoverage": 1.0},
        "visualInputPlanSummary": {"routeDistribution": {"full_page": 1}},
        "retrySummary": {"outcomes": {"succeeded": 1}},
        "extractionPressure": {"selectedTaskCount": 2},
        "safeOutcomeSummary": {"unsafeFailureCount": 0},
        "qualitySummary": {"documents": 1},
        "repeatabilityFingerprints": {
            "documentFamily": "doc-family",
            "semanticRegions": "semantic",
            "plannerTasks": "planner",
            "candidateFingerprints": "candidates",
            "canonicalOutput": "canonical",
            "reviewTasks": "review",
            "rejectionDistribution": "rejections",
        },
        "acceptanceGates": {
            "hardCorrectnessInvariants": {
                "status": "passed",
                "totalViolationCount": 0,
            },
            "goldCorpusQuality": {
                "status": "not_evaluated",
                "missingMetrics": [],
            },
            "operationalSLOs": {
                "status": "passed",
                "metrics": {
                    "targetQueueDeadLetterCount": 0,
                },
                "gates": {
                    "targetQueueDeadLetters": {"status": "passed", "violationCount": 0},
                    "classifiedOperationalFailures": {"status": "passed", "violationCount": 0},
                    "retrySuccessRate": {"status": "passed", "violationCount": 0},
                    "runtimeFailureRates": {"status": "passed", "violationCount": 0},
                    "runawayFanout": {"status": "passed", "violationCount": 0},
                    "retrySafeJobs": {"status": "passed", "violationCount": 0},
                },
            },
        },
    }


def _missing_telemetry_examples() -> list[dict[str, object]]:
    return [
        {
            "reason": "missing_run_id",
            "documentId": None,
            "entityId": "invoice.total_amount",
        },
        {
            "reason": "missing_planner_version",
            "documentId": None,
            "entityId": "invoice.total_amount",
        },
        {
            "reason": "missing_candidate_fingerprint",
            "documentId": None,
            "entityId": "invoice.total_amount",
        },
        {
            "reason": "missing_candidate_gate_version",
            "documentId": None,
            "entityId": "invoice.total_amount",
        },
        {
            "reason": "missing_contract_registry_version",
            "documentId": None,
            "entityId": "invoice.total_amount",
        },
        {
            "reason": "missing_region_envelope_version",
            "documentId": None,
            "entityId": "invoice.total_amount",
        },
    ]


def _semantic_plan_lineage() -> dict[str, str]:
    return {
        "plan_id": "plan-1",
        "plan_task_id": "plan-task-1",
        "semantic_annotation_id": "annotation-1",
    }
