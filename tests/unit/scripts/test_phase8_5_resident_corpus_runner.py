from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4


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


def _report(*, hard_status: str) -> dict[str, object]:
    return {
        "runId": "phase85-resident",
        "runManifest": {},
        "plannerSummary": {},
        "candidateAdmissionSummary": {},
        "envelopeSummary": {},
        "visualInputPlanSummary": {},
        "retrySummary": {},
        "extractionPressure": {},
        "safeOutcomeSummary": {},
        "qualitySummary": {},
        "repeatabilityFingerprints": {
            "plannerTasks": "planner",
            "candidateFingerprints": "candidates",
        },
        "acceptanceGates": {
            "hardCorrectnessInvariants": {"status": hard_status},
            "goldCorpusQuality": {"status": "not_evaluated"},
            "operationalSLOs": {"status": "passed"},
        },
    }
