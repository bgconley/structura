from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.region_envelope import REGION_ENVELOPE_VERSION
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)
from lib.model_runtime.reliability_report import (
    PIPELINE_VERSION,
    build_phase85_reliability_report,
)
from lib.semantic_annotations.extraction_plan_repository import PLANNER_VERSION
from lib.semantic_annotations.prompting import SMART_PROMPT_VERSION


def test_reliability_report_includes_run_manifest_and_lineage_summaries() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-20260604-smoke-001",
        title_prefix="Phase 8.5 Smoke",
        documents=[_document_report()],
    )

    assert report["runId"] == "phase85-20260604-smoke-001"
    assert report["fixtureType"] == "deterministic_fixture"
    assert datetime.fromisoformat(str(report["measuredAt"])).tzinfo is not None
    assert report["runManifest"]["run_id"] == "phase85-20260604-smoke-001"
    assert report["runManifest"]["pipeline_version"] == PIPELINE_VERSION
    assert report["runManifest"]["model_mode"] == "fixture"
    assert report["runManifest"]["semantic_profile"] == QWEN_SEMANTIC_PROFILE
    assert report["runManifest"]["semantic_prompt_version"] == SMART_PROMPT_VERSION
    assert report["runManifest"]["granite_profile"] == GRANITE_VISION_PROFILE
    assert report["runManifest"]["text_embedding_profile"] == TEXT_EMBED_PROFILE
    assert report["runManifest"]["visual_embedding_profile"] == VISUAL_EMBED_PROFILE
    assert report["runManifest"]["planner_version"] == PLANNER_VERSION
    assert report["runManifest"]["candidate_gate_version"] == CANDIDATE_GATE_VERSION
    assert report["runManifest"]["contract_registry_version"] == CONTRACT_REGISTRY_VERSION
    assert report["runManifest"]["region_envelope_version"] == REGION_ENVELOPE_VERSION
    assert report["plannerSummary"] == {
        "runId": "phase85-20260604-smoke-001",
        "plannerVersion": PLANNER_VERSION,
        "selectedTaskCount": 1,
        "skippedTaskCount": 1,
        "abstentionCount": 0,
        "missingContractCount": 1,
        "missingGroundingCount": 0,
        "incompatibleSchemaCount": 0,
        "duplicateSuppressedCount": 1,
        "contractResolutionModes": {"exact": 1, "missing": 1},
    }
    assert report["candidateAdmissionSummary"]["runId"] == "phase85-20260604-smoke-001"
    assert report["candidateAdmissionSummary"]["candidateGateVersion"] == CANDIDATE_GATE_VERSION
    assert report["candidateAdmissionSummary"]["admittedCount"] == 1
    assert report["candidateAdmissionSummary"]["rejectedCount"] == 1
    assert report["candidateAdmissionSummary"]["rejectionReasons"] == {
        "missing_concrete_evidence": 1
    }
    assert report["qualitySummary"] == {
        "documents": 1,
        "reviewRequiredDocuments": 1,
        "reviewStatusCounts": {"needs_review": 1},
    }


def test_reliability_report_summarizes_envelopes_visual_routes_and_safe_outcomes() -> None:
    report = build_phase85_reliability_report(
        run_id="phase85-20260604-smoke-001",
        title_prefix="Phase 8.5 Smoke",
        documents=[_document_report()],
    )

    assert report["envelopeSummary"] == {
        "facts": 1,
        "lineItems": 2,
        "tableRows": 3,
        "observations": 1,
        "concreteEvidenceCoverage": 0.75,
    }
    assert report["visualInputPlanSummary"]["routeDistribution"] == {"full_page": 1}
    assert report["retrySummary"]["outcomes"] == {"succeeded": 1}
    assert report["extractionPressure"] == {
        "plannedTaskCount": 2,
        "selectedTaskCount": 1,
        "selectedTaskCountByBackend": {"granite_region": 1},
        "selectedTaskCountByPage": {"1": 1},
        "maxTasksPerDocumentPolicy": 6,
        "maxTasksPerPagePolicy": 3,
        "budgetExceededCount": 1,
        "estimatedVisualTokens": 2048,
        "estimatedDoclingContextTokens": 512,
    }
    assert report["safeOutcomeSummary"] == {
        "safeAbstentionCount": 0,
        "safeSkipCount": 1,
        "safeRejectionCount": 1,
        "unsafeFailureCount": 0,
    }


def test_reliability_report_fingerprints_are_stable_for_deterministic_runs() -> None:
    first = build_phase85_reliability_report(
        run_id="phase85-20260604-smoke-001",
        title_prefix="Phase 8.5 Smoke",
        documents=[_document_report()],
    )
    second = build_phase85_reliability_report(
        run_id="phase85-20260604-smoke-001",
        title_prefix="Phase 8.5 Smoke",
        documents=[deepcopy(_document_report())],
    )

    assert first["repeatabilityFingerprints"] == second["repeatabilityFingerprints"]
    assert set(first["repeatabilityFingerprints"]) == {
        "documentFamily",
        "semanticRegions",
        "plannerTasks",
        "candidateFingerprints",
        "canonicalOutput",
        "reviewTasks",
        "rejectionDistribution",
    }


def _document_report() -> dict[str, object]:
    return {
        "document": {
            "id": "doc-1",
            "document_family": "invoice",
            "review_status": "needs_review",
        },
        "jobs": [
            {"queue_name": "extraction", "job_type": "extract", "status": "succeeded", "count": 1}
        ],
        "semantic": [
            {
                "quality_mode": "smart",
                "prompt_version": SMART_PROMPT_VERSION,
                "review_required": True,
                "document_type": "invoice",
            }
        ],
        "semanticRegions": [
            {
                "semantic_region_id": "region-1",
                "semantic_annotation_id": "annotation-1",
                "page_number": 1,
                "semantic_type": "invoice_line_item_table",
                "granite_task": "tables_json",
                "target_schema": "invoice",
                "grounding_kind": "table",
                "review_required": True,
            }
        ],
        "planner": [
            {
                "run_id": "phase85-20260604-smoke-001",
                "planner_version": PLANNER_VERSION,
                "selected_task_count": 1,
                "skipped_task_count": 1,
                "abstention_count": 0,
                "missing_contract_count": 1,
                "missing_grounding_count": 0,
                "incompatible_schema_count": 0,
                "duplicate_suppressed_count": 1,
                "report_json": {
                    "maxTasksPerDocumentPolicy": 6,
                    "maxTasksPerPagePolicy": 3,
                    "estimatedDoclingContextTokens": 512,
                },
            }
        ],
        "plannerTasks": [
            {
                "id": "task-1",
                "status": "selected",
                "extractor_backend": "granite_region",
                "page_number": 1,
                "compatibility_mode": "exact",
                "model_output_schema_name": "granite_invoice_line_items.v1",
                "task_json": {"estimatedVisualTokens": 2048},
            },
            {
                "id": "task-2",
                "status": "skipped_budget_exceeded",
                "extractor_backend": "granite_region",
                "page_number": 1,
                "compatibility_mode": "missing",
                "model_output_schema_name": None,
                "task_json": {},
            },
        ],
        "admissionEvents": [
            {
                "run_id": "phase85-20260604-smoke-001",
                "planner_version": PLANNER_VERSION,
                "candidate_gate_version": CANDIDATE_GATE_VERSION,
                "contract_registry_version": CONTRACT_REGISTRY_VERSION,
                "region_envelope_version": REGION_ENVELOPE_VERSION,
                "candidate_kind": "line_item",
                "candidate_fingerprint": "line-fp-1",
                "decision": "admitted_review_required",
                "reasons": [],
                "evidence_concrete": True,
            },
            {
                "run_id": "phase85-20260604-smoke-001",
                "planner_version": PLANNER_VERSION,
                "candidate_gate_version": CANDIDATE_GATE_VERSION,
                "contract_registry_version": CONTRACT_REGISTRY_VERSION,
                "region_envelope_version": REGION_ENVELOPE_VERSION,
                "candidate_kind": "field",
                "candidate_fingerprint": "field-fp-1",
                "decision": "rejected_missing_evidence",
                "reasons": ["missing_concrete_evidence"],
                "evidence_concrete": False,
            },
        ],
        "extractions": [
            {
                "status": "completed",
                "review_status": "needs_review",
                "validation_json": {"needs_review": True},
                "normalization_json": {
                    "regionEnvelope": {
                        "facts": [{"field_path": "invoice.total"}],
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
                "visual_plan": {"route": "full_page"},
                "visual_input_attempts": [{"outcome": "succeeded"}],
            }
        ],
        "fields": [{"field_path": "invoice.total", "value": "10.00", "status": "needs_review"}],
        "lineItems": [{"description": "Service", "net_amount": "10.00", "status": "needs_review"}],
        "observations": [],
        "reviewTasks": [{"id": "review-1", "status": "open"}],
    }
