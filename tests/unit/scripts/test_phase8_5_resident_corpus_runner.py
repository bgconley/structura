from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
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


def test_resident_corpus_runner_cli_imports_from_repo_root() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/gpu/run_phase8_5_resident_corpus.py",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Run PDFs through the resident Phase 8.5 live pipeline" in result.stdout


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


def test_cancel_text_embedding_jobs_cancels_claimed_worker_race(monkeypatch) -> None:
    runner = _load_resident_runner()
    document_id = uuid4()
    cursor = _RecordingCursor(rows=[{"id": uuid4()}, {"id": uuid4()}])
    connection = _RecordingConnection(cursor)

    monkeypatch.setattr(runner, "db_connection", lambda: connection)

    cancelled = runner._cancel_text_embedding_jobs(
        [document_id],
        run_id="phase85-pass",
        requested_by="phase8_5_resident_acceptance",
    )

    assert cancelled == 2
    assert connection.committed
    sql, params = cursor.calls[0]
    assert "lease_expires_at = NULL" in sql
    assert "status::text = ANY(%s)" in sql
    assert params[-1] == ["failed", "leased", "queued", "running"]


def test_active_job_preflight_scopes_to_phase85_target_queues(monkeypatch) -> None:
    runner = _load_resident_runner()
    cursor = _RecordingCursor(rows=[])
    connection = _RecordingConnection(cursor)

    monkeypatch.setattr(runner, "db_connection", lambda: connection)

    assert runner._active_job_counts() == []

    sql, params = cursor.calls[0]
    assert "queue_name = ANY(%s)" in sql
    assert params[1] == sorted(runner.TARGET_FAILURE_QUEUES)
    assert "relationships" not in params[1]


def test_planner_task_report_query_derives_missing_page_number() -> None:
    runner = _load_resident_runner()

    page_number_expr = (
        "COALESCE(task.page_number, psa.page_number, "
        "dp.page_number, dep.page_number, dtp.page_number)"
    )
    assert page_number_expr in runner._PLANNER_TASKS_SQL
    assert "task.visual_plan_summary" in runner._PLANNER_TASKS_SQL
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


def test_resident_manifest_carries_private_gold_metrics_into_ingest_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _load_resident_runner()
    pdf = tmp_path / "gold.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    manifest = tmp_path / "phase8_5_resident_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "path": str(pdf),
                        "goldMetrics": _gold_metrics(),
                        "goldThresholds": _gold_thresholds(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    document_id = uuid4()

    monkeypatch.setattr(runner, "_resolve_owner", lambda: (uuid4(), uuid4()))
    monkeypatch.setattr(
        runner,
        "ingest_document_path",
        lambda *_args, **_kwargs: SimpleNamespace(
            document_id=document_id,
            sha256="a" * 64,
        ),
    )

    entries = runner._resolve_corpus_entries(
        SimpleNamespace(pdf=None, manifest=manifest),
    )
    documents = runner._ingest_documents(
        entries,
        run_id="phase85-gold",
        title_prefix="Phase 8.5 Gold",
        requested_by="test",
    )

    assert [entry.path for entry in entries] == [pdf]
    assert documents[0]["document_id"] == document_id
    assert documents[0]["goldMetrics"]["familyTop1Accuracy"] == 0.92
    assert documents[0]["goldThresholds"]["expectedCalibrationError"] == 0.05
    assert runner._gold_metadata_by_document_id(documents) == {
        document_id: {
            "goldMetrics": documents[0]["goldMetrics"],
            "goldThresholds": documents[0]["goldThresholds"],
        }
    }


def test_resident_manifest_carries_corpus_gold_metrics_into_ingest_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _load_resident_runner()
    pdf = tmp_path / "gold.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    manifest = tmp_path / "phase8_5_resident_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "goldMetrics": _gold_metrics(),
                "goldThresholds": _gold_thresholds(),
                "documents": [{"path": str(pdf)}],
            }
        ),
        encoding="utf-8",
    )
    document_id = uuid4()

    monkeypatch.setattr(runner, "_resolve_owner", lambda: (uuid4(), uuid4()))
    monkeypatch.setattr(
        runner,
        "ingest_document_path",
        lambda *_args, **_kwargs: SimpleNamespace(
            document_id=document_id,
            sha256="a" * 64,
        ),
    )

    documents = runner._ingest_documents(
        runner._resolve_corpus_entries(SimpleNamespace(pdf=None, manifest=manifest)),
        run_id="phase85-gold",
        title_prefix="Phase 8.5 Gold",
        requested_by="test",
    )

    assert documents[0]["goldMetrics"]["familyTop1Accuracy"] == 0.92
    assert documents[0]["goldThresholds"]["expectedCalibrationError"] == 0.05


def test_resident_manifest_carries_holdout_metadata_into_report_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runner = _load_resident_runner()
    pdf = tmp_path / "holdout.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    manifest = tmp_path / "phase8_5_resident_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "path": str(pdf),
                        "holdoutLabel": "private_holdout",
                        "overfittingGuards": {
                            "pinnedCorpus": False,
                            "privateHoldout": True,
                            "syntheticAdversarial": False,
                            "usedForPromptTuning": False,
                            "reviewedBeforeDefaultFlip": True,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    document_id = uuid4()

    monkeypatch.setattr(runner, "_resolve_owner", lambda: (uuid4(), uuid4()))
    monkeypatch.setattr(
        runner,
        "ingest_document_path",
        lambda *_args, **_kwargs: SimpleNamespace(
            document_id=document_id,
            sha256="a" * 64,
        ),
    )

    documents = runner._ingest_documents(
        runner._resolve_corpus_entries(SimpleNamespace(pdf=None, manifest=manifest)),
        run_id="phase85-holdout",
        title_prefix="Phase 8.5 Holdout",
        requested_by="test",
    )

    assert documents[0]["holdoutLabel"] == "private_holdout"
    assert documents[0]["overfittingGuards"]["privateHoldout"] is True
    assert runner._gold_metadata_by_document_id(documents) == {
        document_id: {
            "holdoutLabel": "private_holdout",
            "overfittingGuards": documents[0]["overfittingGuards"],
        }
    }


def test_fetch_report_attaches_gold_metadata_to_reliability_report(monkeypatch) -> None:
    runner = _load_resident_runner()
    document_id = uuid4()
    cursor = _FetchReportCursor(
        row={
            "id": document_id,
            "title": "Gold document",
            "original_filename": "gold.pdf",
            "document_family": "invoice",
            "document_subtype": None,
            "family_confidence": None,
            "review_status": "needs_review",
            "page_count": 1,
            "document_date": None,
            "counterparty_display": None,
        }
    )
    connection = _RecordingConnection(cursor)

    monkeypatch.setattr(runner, "db_connection", lambda: connection)
    monkeypatch.setattr(runner, "_rows_for_document", lambda *_args: [])
    monkeypatch.setattr(runner, "_fields_for_document", lambda *_args: [])

    report = runner._fetch_report(
        [document_id],
        run_id="phase85-gold",
        title_prefix="Phase 8.5 Gold",
        gold_metadata_by_document_id={
            document_id: {
                "goldMetrics": _gold_metrics(),
                "goldThresholds": _gold_thresholds(),
            }
        },
    )

    assert report["documents"][0]["goldMetrics"]["familyTop1Accuracy"] == 0.92
    assert report["acceptanceGates"]["goldCorpusQuality"]["status"] == "passed"


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
            "vision_fallback_provider": "granite",
            "qwen_vision_fallback_enabled": False,
            "text_embedding_profile": TEXT_EMBED_PROFILE,
            "visual_embedding_profile": VISUAL_EMBED_PROFILE,
            **_task12_manifest_lineage(),
        },
        "plannerSummary": {"selectedTaskCount": 1},
        "candidateAdmissionSummary": {"admittedCount": 1, "rejectedCount": 0},
        "contractSummary": {"contractedTaskCount": 1, "missingContractTaskCount": 0},
        "evidenceSummary": {"concreteEvidenceCoverage": 1.0},
        "dedupeSummary": {"totalDuplicateSuppressionCount": 0},
        "envelopeSummary": {"concreteEvidenceCoverage": 1.0},
        "visualInputPlanSummary": {"routeDistribution": {"full_page": 1}},
        "retrySummary": {"outcomes": {"succeeded": 1}},
        "extractionPressure": {"selectedTaskCount": 1},
        "safeOutcomeSummary": {"unsafeFailureCount": 0},
        "qualitySummary": {"documents": 1},
        "documentOutcomes": [
            {
                "documentId": "doc-private-1",
                "filename": "private-holdout.pdf",
                "documentFamily": "invoice",
                "releaseOutcome": "needs_human_review",
                "abstentionClass": "not_abstained",
                "holdoutLabel": "private_holdout",
                "overfittingGuards": {
                    "pinnedCorpus": False,
                    "privateHoldout": True,
                    "syntheticAdversarial": False,
                    "usedForPromptTuning": False,
                    "reviewedBeforeDefaultFlip": True,
                },
            }
        ],
        "documentOutcomeSummary": {
            "documentCount": 1,
            "outcomeCounts": {"needs_human_review": 1},
            "abstentionClassCounts": {"not_abstained": 1},
            "holdoutLabelCounts": {"private_holdout": 1},
            "pipelineFailedCount": 0,
            "holdoutDocumentCount": 1,
            "adversarialDocumentCount": 0,
            "promptTunedHoldoutCount": 0,
            "reviewedHoldoutDocumentCount": 1,
        },
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


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self.cursor_obj = cursor
        self.committed = False

    def __enter__(self) -> _RecordingConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def cursor(self) -> _RecordingCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class _RecordingCursor:
    def __init__(self, *, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> _RecordingCursor:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


class _FetchReportCursor(_RecordingCursor):
    def __init__(self, *, row: dict[str, object]) -> None:
        super().__init__(rows=[])
        self.row = row

    def fetchone(self) -> dict[str, object]:
        return self.row


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
        "decoding": {"temperature": 0, "top_p": None, "seed": 0},
    }


def _gold_metrics() -> dict[str, object]:
    return {
        "familyTop1Accuracy": 0.92,
        "familyTop2Accuracy": 0.98,
        "fieldPrecisionByFamily": {"invoice": 0.93},
        "fieldRecallByFamily": {"invoice": 0.88},
        "fieldF1ByFamily": {"invoice": 0.9},
        "lineItemRowPrecisionByFamily": {"invoice": 0.94},
        "lineItemRowRecallByFamily": {"invoice": 0.86},
        "lineItemRowF1ByFamily": {"invoice": 0.895},
        "amountDateNormalizationAccuracy": 0.96,
        "evidenceLocatorCompleteness": 0.97,
        "duplicateRate": 0.02,
        "reviewBurden": 0.24,
        "falseCanonicalPromotionRate": 0.0,
        "repeatabilityStability": 0.99,
        "confidenceCalibrationByFamilyField": {"invoice.total_amount": 0.04},
        "expectedCalibrationError": 0.04,
        "precisionAtConfidenceBuckets": {"0.90-1.00": 0.96},
        "reviewBurdenAtConfidenceThresholds": {"0.80": 0.18},
    }


def _gold_thresholds() -> dict[str, object]:
    return {
        "familyTop1Accuracy": 0.9,
        "familyTop2Accuracy": 0.95,
        "fieldPrecisionByFamily": 0.9,
        "fieldRecallByFamily": 0.85,
        "fieldF1ByFamily": 0.88,
        "lineItemRowPrecisionByFamily": 0.88,
        "lineItemRowRecallByFamily": 0.85,
        "lineItemRowF1ByFamily": 0.88,
        "amountDateNormalizationAccuracy": 0.95,
        "evidenceLocatorCompleteness": 0.95,
        "duplicateRate": 0.05,
        "reviewBurden": 0.3,
        "falseCanonicalPromotionRate": 0.0,
        "repeatabilityStability": 0.98,
        "confidenceCalibrationByFamilyField": 0.08,
        "expectedCalibrationError": 0.05,
        "precisionAtConfidenceBuckets": 0.8,
        "reviewBurdenAtConfidenceThresholds": 0.25,
    }
