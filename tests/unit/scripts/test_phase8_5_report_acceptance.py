from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)


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
        "fixtureType": "model_backed",
        "measuredAt": "2026-06-04T12:00:00+00:00",
        "runManifest": {
            "pipeline_version": "phase8_5_reliability_v1",
            "model_mode": "live",
            "semantic_profile": QWEN_SEMANTIC_PROFILE,
            "granite_profile": GRANITE_VISION_PROFILE,
            "text_embedding_profile": TEXT_EMBED_PROFILE,
            "visual_embedding_profile": VISUAL_EMBED_PROFILE,
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
            "documentFamily": "stable-family",
            "semanticRegions": "stable-semantic",
            "plannerTasks": "stable-planner",
            "candidateFingerprints": candidate_fingerprint,
            "canonicalOutput": "stable-canonical",
            "reviewTasks": "stable-review",
            "rejectionDistribution": "stable-rejections",
        },
        "acceptanceGates": {
            "hardCorrectnessInvariants": {"status": "passed"},
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
