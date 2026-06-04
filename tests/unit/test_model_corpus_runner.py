from __future__ import annotations

import json
import subprocess
import sys

import pytest

from lib.model_runtime.reliability_report import PIPELINE_VERSION
from scripts.run_model_corpus import evaluate_model_corpus_manifest


def test_model_corpus_runner_requires_model_backed_evidence_when_requested() -> None:
    payload = _manifest(fixture_type="deterministic_fixture")

    with pytest.raises(SystemExit, match="model-backed"):
        evaluate_model_corpus_manifest(payload, require_model_backed=True)


def test_model_corpus_runner_enforces_required_sections_and_thresholds() -> None:
    payload = _manifest(fixture_type="model_backed")
    result = evaluate_model_corpus_manifest(payload, require_model_backed=True)

    assert result["fixtureType"] == "model_backed"
    assert result["runManifest"]["pipeline_version"] == PIPELINE_VERSION
    assert result["runManifest"]["run_id"] == "phase85-fixture-run"
    assert result["evidence"]["qwen"]["evidencePath"].endswith("/qwen-report.json")
    assert result["metrics"]["provenance_truth_rate"] == 1.0
    assert result["goldCorpusMetrics"]["status"] == "passed"
    assert result["goldCorpusMetrics"]["metrics"]["expectedCalibrationError"]["status"] == "passed"

    payload["metrics"]["visual_embedding_hit_rate_at_k"] = 0.2
    with pytest.raises(SystemExit, match="visual_embedding_hit_rate_at_k"):
        evaluate_model_corpus_manifest(payload, require_model_backed=True)


def test_model_corpus_runner_requires_gold_corpus_baseline_metrics() -> None:
    payload = _manifest(fixture_type="model_backed")
    del payload["goldMetrics"]["expectedCalibrationError"]

    with pytest.raises(SystemExit, match="expectedCalibrationError"):
        evaluate_model_corpus_manifest(payload, require_model_backed=True)


def test_model_corpus_runner_requires_traceable_live_evidence_for_model_backed_manifest() -> None:
    payload = _manifest(fixture_type="model_backed")
    del payload["evidence"]["qwen"]["evidencePath"]  # type: ignore[index]

    with pytest.raises(SystemExit, match="qwen.*evidencePath"):
        evaluate_model_corpus_manifest(payload, require_model_backed=True)

    payload = _manifest(fixture_type="model_backed")
    payload["evidence"]["granite"]["runId"] = ""  # type: ignore[index]

    with pytest.raises(SystemExit, match="granite.*runId"):
        evaluate_model_corpus_manifest(payload, require_model_backed=True)


def test_model_corpus_example_manifest_is_valid() -> None:
    payload = json.loads(
        open("tests/fixtures/model_corpus/phase8_5_model_manifest.example.json").read()
    )

    result = evaluate_model_corpus_manifest(payload, require_model_backed=False)

    assert result["fixtureType"] == "deterministic_fixture"


def test_model_corpus_script_runs_as_direct_entrypoint() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--manifest",
            "tests/fixtures/model_corpus/phase8_5_model_manifest.example.json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["fixtureType"] == "deterministic_fixture"
    assert payload["runManifest"]["pipeline_version"] == PIPELINE_VERSION


def _manifest(*, fixture_type: str) -> dict[str, object]:
    return {
        "fixtureType": fixture_type,
        "runId": "phase85-fixture-run",
        "evidence": {
            "qwen": _evidence("qwen3-vl-8b-instruct-nvfp4-local:v1", "qwen"),
            "granite": _evidence("granite-4.0-3b-vision-bf16:v1", "granite"),
            "textEmbedding": _evidence("qwen3-embedding-4b-1536:v1", "text"),
            "visualEmbedding": _evidence("qwen3-vl-embedding-2b-2048:v1", "visual"),
        },
        "metrics": {
            "qwen_handwriting_route_success_rate": 1.0,
            "qwen_review_required_rate": 1.0,
            "granite_table_structure_score": 0.9,
            "granite_kvp_exact_match": 0.85,
            "text_embedding_hit_rate_at_k": 0.95,
            "visual_embedding_hit_rate_at_k": 0.9,
            "hybrid_hit_rate_at_k": 1.0,
            "provenance_truth_rate": 1.0,
        },
        "thresholds": {
            "qwen_handwriting_route_success_rate": 0.8,
            "qwen_review_required_rate": 0.9,
            "granite_table_structure_score": 0.75,
            "granite_kvp_exact_match": 0.75,
            "text_embedding_hit_rate_at_k": 0.8,
            "visual_embedding_hit_rate_at_k": 0.75,
            "hybrid_hit_rate_at_k": 0.85,
            "provenance_truth_rate": 1.0,
        },
        "goldMetrics": {
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
        },
        "goldThresholds": {
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
        },
    }


def _evidence(profile: str, slug: str) -> dict[str, object]:
    return {
        "profile": profile,
        "runId": f"phase85-fixture-run-{slug}",
        "measuredAt": "2026-06-04T12:00:00Z",
        "evidencePath": f"/srv/structura/objects/exports/phase85-runs/{slug}-report.json",
    }
