from __future__ import annotations

import importlib.util
from pathlib import Path


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
