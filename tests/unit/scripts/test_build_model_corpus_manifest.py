from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)
from lib.model_runtime.reliability_versions import PIPELINE_VERSION


def test_build_model_corpus_manifest_writes_valid_release_manifest(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    artifacts = {
        "qwen": evidence_dir / "qwen.json",
        "granite": evidence_dir / "granite.json",
        "textEmbedding": evidence_dir / "text.json",
        "visualEmbedding": evidence_dir / "visual.json",
    }
    metrics = _metrics()
    _write_artifact(
        artifacts["qwen"],
        run_id="phase85-qwen-run",
        profile=QWEN_SEMANTIC_PROFILE,
        run_manifest_profiles={"semantic_profile": QWEN_SEMANTIC_PROFILE},
        metrics=metrics,
    )
    _write_artifact(
        artifacts["granite"],
        run_id="phase85-granite-run",
        profile=GRANITE_VISION_PROFILE,
        run_manifest_profiles={"granite_profile": GRANITE_VISION_PROFILE},
        metrics=metrics,
    )
    _write_artifact(
        artifacts["textEmbedding"],
        run_id="phase85-text-run",
        profile=TEXT_EMBED_PROFILE,
        run_manifest_profiles={"text_embedding_profile": TEXT_EMBED_PROFILE},
        metrics=metrics,
    )
    _write_artifact(
        artifacts["visualEmbedding"],
        run_id="phase85-visual-run",
        profile=VISUAL_EMBED_PROFILE,
        run_manifest_profiles={"visual_embedding_profile": VISUAL_EMBED_PROFILE},
        metrics=metrics,
    )
    thresholds = tmp_path / "thresholds.json"
    gold_metrics = tmp_path / "gold-metrics.json"
    gold_thresholds = tmp_path / "gold-thresholds.json"
    thresholds.write_text(json.dumps(_thresholds()), encoding="utf-8")
    gold_metrics.write_text(json.dumps(_gold_metrics()), encoding="utf-8")
    gold_thresholds.write_text(json.dumps(_gold_thresholds()), encoding="utf-8")
    output = tmp_path / "phase8_5_model_manifest.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_model_corpus_manifest.py",
            "--output",
            str(output),
            "--run-id",
            "phase85-private-release",
            "--model-mode",
            "live",
            "--qwen-evidence",
            str(artifacts["qwen"]),
            "--granite-evidence",
            str(artifacts["granite"]),
            "--text-embedding-evidence",
            str(artifacts["textEmbedding"]),
            "--visual-embedding-evidence",
            str(artifacts["visualEmbedding"]),
            "--thresholds-json",
            str(thresholds),
            "--gold-metrics-json",
            str(gold_metrics),
            "--gold-thresholds-json",
            str(gold_thresholds),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["fixtureType"] == "model_backed"
    assert payload["runManifest"]["model_mode"] == "live"
    assert payload["runManifest"]["semantic_profile"] == QWEN_SEMANTIC_PROFILE
    assert payload["evidence"]["qwen"]["runId"] == "phase85-qwen-run"
    assert Path(payload["evidence"]["qwen"]["evidencePath"]).is_absolute()

    validate = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert validate.returncode == 0, validate.stderr


def test_build_model_corpus_manifest_rejects_missing_evidence_metrics(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "qwen.json"
    artifact = _artifact(
        run_id="phase85-qwen-run",
        profile=QWEN_SEMANTIC_PROFILE,
        run_manifest_profiles={"semantic_profile": QWEN_SEMANTIC_PROFILE},
        metrics={},
    )
    evidence.write_text(json.dumps(artifact), encoding="utf-8")
    shared = tmp_path / "shared.json"
    _write_artifact(
        shared,
        run_id="phase85-shared-run",
        profile=GRANITE_VISION_PROFILE,
        run_manifest_profiles={"granite_profile": GRANITE_VISION_PROFILE},
        metrics=_metrics(),
    )
    thresholds = tmp_path / "thresholds.json"
    gold_metrics = tmp_path / "gold-metrics.json"
    gold_thresholds = tmp_path / "gold-thresholds.json"
    thresholds.write_text(json.dumps(_thresholds()), encoding="utf-8")
    gold_metrics.write_text(json.dumps(_gold_metrics()), encoding="utf-8")
    gold_thresholds.write_text(json.dumps(_gold_thresholds()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_model_corpus_manifest.py",
            "--output",
            str(tmp_path / "phase8_5_model_manifest.json"),
            "--run-id",
            "phase85-private-release",
            "--model-mode",
            "live",
            "--qwen-evidence",
            str(evidence),
            "--granite-evidence",
            str(shared),
            "--text-embedding-evidence",
            str(shared),
            "--visual-embedding-evidence",
            str(shared),
            "--thresholds-json",
            str(thresholds),
            "--gold-metrics-json",
            str(gold_metrics),
            "--gold-thresholds-json",
            str(gold_thresholds),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "qwen_handwriting_route_success_rate" in result.stderr


def test_build_model_corpus_manifest_rejects_wrong_section_profile(
    tmp_path: Path,
) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    metrics = _metrics()
    qwen = evidence_dir / "qwen.json"
    granite = evidence_dir / "granite.json"
    text = evidence_dir / "text.json"
    visual = evidence_dir / "visual.json"
    _write_artifact(
        qwen,
        run_id="phase85-qwen-run",
        profile=QWEN_SEMANTIC_PROFILE,
        run_manifest_profiles={"semantic_profile": QWEN_SEMANTIC_PROFILE},
        metrics=metrics,
    )
    _write_artifact(
        granite,
        run_id="phase85-granite-run",
        profile=GRANITE_VISION_PROFILE,
        run_manifest_profiles={"granite_profile": GRANITE_VISION_PROFILE},
        metrics=metrics,
    )
    _write_artifact(
        text,
        run_id="phase85-text-run",
        profile=GRANITE_VISION_PROFILE,
        run_manifest_profiles={"text_embedding_profile": GRANITE_VISION_PROFILE},
        metrics=metrics,
    )
    _write_artifact(
        visual,
        run_id="phase85-visual-run",
        profile=VISUAL_EMBED_PROFILE,
        run_manifest_profiles={"visual_embedding_profile": VISUAL_EMBED_PROFILE},
        metrics=metrics,
    )
    thresholds = tmp_path / "thresholds.json"
    gold_metrics = tmp_path / "gold-metrics.json"
    gold_thresholds = tmp_path / "gold-thresholds.json"
    thresholds.write_text(json.dumps(_thresholds()), encoding="utf-8")
    gold_metrics.write_text(json.dumps(_gold_metrics()), encoding="utf-8")
    gold_thresholds.write_text(json.dumps(_gold_thresholds()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_model_corpus_manifest.py",
            "--output",
            str(tmp_path / "phase8_5_model_manifest.json"),
            "--run-id",
            "phase85-private-release",
            "--model-mode",
            "live",
            "--qwen-evidence",
            str(qwen),
            "--granite-evidence",
            str(granite),
            "--text-embedding-evidence",
            str(text),
            "--visual-embedding-evidence",
            str(visual),
            "--thresholds-json",
            str(thresholds),
            "--gold-metrics-json",
            str(gold_metrics),
            "--gold-thresholds-json",
            str(gold_thresholds),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "textEmbedding" in result.stderr
    assert TEXT_EMBED_PROFILE in result.stderr


def _write_artifact(
    path: Path,
    *,
    run_id: str,
    profile: str,
    run_manifest_profiles: dict[str, str],
    metrics: dict[str, float],
) -> None:
    path.write_text(
        json.dumps(
            _artifact(
                run_id=run_id,
                profile=profile,
                run_manifest_profiles=run_manifest_profiles,
                metrics=metrics,
            )
        ),
        encoding="utf-8",
    )


def _artifact(
    *,
    run_id: str,
    profile: str,
    run_manifest_profiles: dict[str, str],
    metrics: dict[str, float],
) -> dict[str, Any]:
    return {
        "fixtureType": "model_backed",
        "runId": run_id,
        "measuredAt": "2026-06-04T12:00:00+00:00",
        "profile": profile,
        "runManifest": {
            "run_id": run_id,
            "pipeline_version": PIPELINE_VERSION,
            "model_mode": "live",
            **run_manifest_profiles,
        },
        "metrics": metrics,
        "checks": {"status": "passed"},
    }


def _metrics() -> dict[str, float]:
    return {
        "qwen_handwriting_route_success_rate": 1.0,
        "qwen_review_required_rate": 1.0,
        "granite_table_structure_score": 0.9,
        "granite_kvp_exact_match": 0.9,
        "text_embedding_hit_rate_at_k": 0.95,
        "visual_embedding_hit_rate_at_k": 0.9,
        "hybrid_hit_rate_at_k": 0.9,
        "provenance_truth_rate": 1.0,
    }


def _thresholds() -> dict[str, float]:
    return {
        "qwen_handwriting_route_success_rate": 0.8,
        "qwen_review_required_rate": 0.9,
        "granite_table_structure_score": 0.75,
        "granite_kvp_exact_match": 0.75,
        "text_embedding_hit_rate_at_k": 0.8,
        "visual_embedding_hit_rate_at_k": 0.75,
        "hybrid_hit_rate_at_k": 0.85,
        "provenance_truth_rate": 1.0,
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


def _gold_thresholds() -> dict[str, float]:
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
