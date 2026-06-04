from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_phase8_5_report_acceptance_cli_fails_on_repeatability_drift(tmp_path: Path) -> None:
    first = _report("pass-1", candidate_fingerprint="stable")
    second = _report("pass-2", candidate_fingerprint="changed")
    first_path = tmp_path / "pass-1.json"
    second_path = tmp_path / "pass-2.json"
    first_path.write_text(json.dumps(first), encoding="utf-8")
    second_path.write_text(json.dumps(second), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/gpu/phase8_5_report_acceptance.py",
            str(first_path),
            str(second_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "candidateFingerprints" in result.stdout


def _report(run_id: str, *, candidate_fingerprint: str) -> dict[str, object]:
    return {
        "runId": run_id,
        "runManifest": {"pipeline_version": "phase8_5_reliability_v1"},
        "plannerSummary": {},
        "candidateAdmissionSummary": {},
        "envelopeSummary": {},
        "visualInputPlanSummary": {},
        "retrySummary": {},
        "extractionPressure": {},
        "safeOutcomeSummary": {},
        "qualitySummary": {},
        "repeatabilityFingerprints": {
            "plannerTasks": "stable-planner",
            "candidateFingerprints": candidate_fingerprint,
        },
        "acceptanceGates": {
            "hardCorrectnessInvariants": {"status": "passed"},
            "goldCorpusQuality": {"status": "not_evaluated"},
            "operationalSLOs": {"status": "passed"},
        },
    }
