from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

from lib.extraction.candidate_admission_models import CANDIDATE_GATE_VERSION
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.region_envelope import REGION_ENVELOPE_VERSION
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
    get_model_profile,
)
from lib.model_runtime.reliability_versions import (
    GRANITE_PROMPT_VERSION,
    RECONCILER_VERSION,
    VISUAL_INPUT_PLAN_VERSION,
)
from lib.semantic_annotations.extraction_plan_repository import PLANNER_VERSION
from lib.semantic_annotations.prompting import SMART_PROMPT_VERSION


def _load_resident_runner():
    script_path = (
        Path(__file__).resolve().parents[3] / "scripts" / "gpu" / "run_phase8_5_resident_corpus.py"
    )
    spec = importlib.util.spec_from_file_location(
        "run_phase8_5_resident_corpus",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resident_corpus_acceptance_exit_code_fails_failed_report() -> None:
    runner = _load_resident_runner()
    report = _report(hard_status="failed")

    assert runner._acceptance_exit_code(report) == 1


def test_resident_corpus_acceptance_exit_code_allows_passing_resident_report_without_gold() -> None:
    runner = _load_resident_runner()
    report = _report(hard_status="passed")

    assert runner._acceptance_exit_code(report) == 0


def test_terminal_state_ignores_failed_non_target_maintenance_jobs(monkeypatch) -> None:
    runner = _load_resident_runner()
    document_id = uuid4()

    monkeypatch.setattr(
        runner,
        "_job_counts",
        lambda _document_ids: [
            {"queue_name": "ingest", "job_type": "ingest", "status": "failed", "count": 1},
            {"queue_name": "previews", "job_type": "preview", "status": "failed", "count": 1},
            {
                "queue_name": "relationships",
                "job_type": "relate",
                "status": "failed",
                "count": 1,
            },
            {
                "queue_name": "semantic-annotations",
                "job_type": "semantic_annotate",
                "status": "succeeded",
                "count": 1,
            },
        ],
    )
    monkeypatch.setattr(
        runner,
        "_document_progress",
        lambda _document_ids: [{"pages": 1, "semantic_succeeded": 1}],
    )

    done, active, target_dead_letters, _progress = runner._terminal_state([document_id])

    assert done
    assert active == []
    assert target_dead_letters == []


def test_planner_task_report_query_derives_missing_page_number() -> None:
    runner = _load_resident_runner()

    page_number_expr = (
        "COALESCE(task.page_number, psa.page_number, "
        "dp.page_number, dep.page_number, dtp.page_number)"
    )
    assert page_number_expr in runner._PLANNER_TASKS_SQL
    assert "LEFT JOIN semantic_region_annotations region" in runner._PLANNER_TASKS_SQL
    assert "LEFT JOIN document_elements de" in runner._PLANNER_TASKS_SQL
    assert "LEFT JOIN document_tables dt" in runner._PLANNER_TASKS_SQL


def test_candidate_report_queries_project_admission_fingerprints() -> None:
    runner = _load_resident_runner()

    assert "candidate_fingerprint" in runner._FIELDS_SQL
    assert "validation_json ->> 'candidateAdmissionFingerprint'" in runner._FIELDS_SQL
    assert "candidate_fingerprint" in runner._LINE_ITEMS_SQL
    assert "validation_json ->> 'candidateAdmissionFingerprint'" in runner._LINE_ITEMS_SQL
    assert "candidate_fingerprint" in runner._OBSERVATIONS_SQL
    assert "metadata_json ->> 'candidateAdmissionFingerprint'" in runner._OBSERVATIONS_SQL


def _report(*, hard_status: str) -> dict[str, object]:
    return {
        "runId": "phase85-resident",
        "fixtureType": "model_backed",
        "measuredAt": "2026-06-04T12:00:00+00:00",
        "runManifest": {
            "run_id": "phase85-resident",
            "pipeline_version": "phase8_5_reliability_v1",
            "model_mode": "live",
            "semantic_profile": QWEN_SEMANTIC_PROFILE,
            "granite_profile": GRANITE_VISION_PROFILE,
            "text_embedding_profile": TEXT_EMBED_PROFILE,
            "visual_embedding_profile": VISUAL_EMBED_PROFILE,
            **_task12_manifest_lineage(),
        },
        "plannerSummary": {"selectedTaskCount": 1},
        "candidateAdmissionSummary": {"admittedCount": 1, "rejectedCount": 0},
        "envelopeSummary": {"concreteEvidenceCoverage": 1.0},
        "visualInputPlanSummary": {"routeDistribution": {"full_page": 1}},
        "retrySummary": {"outcomes": {"succeeded": 1}},
        "extractionPressure": {"selectedTaskCount": 1},
        "safeOutcomeSummary": {"unsafeFailureCount": 0},
        "qualitySummary": {"documents": 1},
        "repeatabilityFingerprints": {
            "documentFamily": "family",
            "semanticRegions": "semantic",
            "plannerTasks": "planner",
            "candidateFingerprints": "candidates",
            "canonicalOutput": "canonical",
            "reviewTasks": "review",
            "rejectionDistribution": "rejections",
        },
        "acceptanceGates": {
            "hardCorrectnessInvariants": {
                "status": hard_status,
                "totalViolationCount": 0,
            },
            "goldCorpusQuality": {"status": "not_evaluated"},
            "operationalSLOs": {
                "status": "passed",
                "metrics": {"targetQueueDeadLetterCount": 0},
                "gates": _passed_operational_slo_gates(),
            },
        },
    }


def _passed_operational_slo_gates() -> dict[str, dict[str, object]]:
    return {
        "targetQueueDeadLetters": {"status": "passed", "violationCount": 0},
        "classifiedOperationalFailures": {"status": "passed", "violationCount": 0},
        "retrySuccessRate": {"status": "passed", "violationCount": 0},
        "runtimeFailureRates": {"status": "passed", "violationCount": 0},
        "runawayFanout": {"status": "passed", "violationCount": 0},
        "retrySafeJobs": {"status": "passed", "violationCount": 0},
    }


def _task12_manifest_lineage() -> dict[str, object]:
    return {
        "docling_version": "worker-docling-isolated",
        "semantic_prompt_version": SMART_PROMPT_VERSION,
        "granite_model": get_model_profile(GRANITE_VISION_PROFILE).base_model,
        "granite_prompt_version": GRANITE_PROMPT_VERSION,
        "planner_version": PLANNER_VERSION,
        "contract_registry_version": CONTRACT_REGISTRY_VERSION,
        "region_envelope_version": REGION_ENVELOPE_VERSION,
        "candidate_gate_version": CANDIDATE_GATE_VERSION,
        "reconciler_version": RECONCILER_VERSION,
        "visual_input_plan_version": VISUAL_INPUT_PLAN_VERSION,
        "decoding": {"temperature": 0, "top_p": None},
    }
