from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def test_model_corpus_script_requires_existing_model_backed_evidence_paths(
    tmp_path,
) -> None:
    payload = _manifest(fixture_type="model_backed")
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence_sections = payload["evidence"]
    assert isinstance(evidence_sections, dict)
    for section, evidence in evidence_sections.items():
        assert isinstance(evidence, dict)
        evidence["evidencePath"] = f"evidence/{section}.json"
        if section != "qwen":
            (evidence_dir / f"{section}.json").write_text("{}", encoding="utf-8")
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "qwen" in result.stderr
    assert "evidencePath not found" in result.stderr


def test_model_corpus_script_requires_parseable_evidence_artifacts(tmp_path) -> None:
    payload = _manifest(fixture_type="model_backed")
    _write_evidence_artifacts(tmp_path, payload)
    (tmp_path / "evidence" / "qwen.json").write_text("not json", encoding="utf-8")
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "qwen" in result.stderr
    assert "evidencePath must contain a JSON object" in result.stderr


def test_model_corpus_script_requires_matching_evidence_artifact_run_id(tmp_path) -> None:
    payload = _manifest(fixture_type="model_backed")
    _write_evidence_artifacts(tmp_path, payload, fixture_type="model_backed")
    (tmp_path / "evidence" / "granite.json").write_text(
        json.dumps(_evidence_artifact("different-run", fixture_type="model_backed")),
        encoding="utf-8",
    )
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "granite" in result.stderr
    assert "runId mismatch" in result.stderr


def test_model_corpus_script_requires_report_lineage_in_evidence_artifacts(tmp_path) -> None:
    payload = _manifest(fixture_type="model_backed")
    _write_evidence_artifacts(tmp_path, payload)
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "qwen" in result.stderr
    assert "report evidence" in result.stderr


def test_model_corpus_script_rejects_fixture_evidence_artifacts(tmp_path) -> None:
    payload = _manifest(fixture_type="model_backed")
    _write_evidence_artifacts(tmp_path, payload, fixture_type="model_backed")
    (tmp_path / "evidence" / "visualEmbedding.json").write_text(
        json.dumps(
            _evidence_artifact(
                "phase85-fixture-run-visual",
                fixture_type="deterministic_fixture",
            )
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "visualEmbedding" in result.stderr
    assert "fixture-backed" in result.stderr


def test_model_corpus_script_requires_section_metric_evidence(tmp_path) -> None:
    payload = _manifest(fixture_type="model_backed")
    _write_evidence_artifacts(tmp_path, payload, fixture_type="model_backed")
    qwen_evidence = payload["evidence"]["qwen"]  # type: ignore[index]
    assert isinstance(qwen_evidence, dict)
    (tmp_path / qwen_evidence["evidencePath"]).write_text(  # type: ignore[index]
        json.dumps(_evidence_artifact(str(qwen_evidence["runId"]), fixture_type="model_backed")),
        encoding="utf-8",
    )
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "qwen" in result.stderr
    assert "qwen_handwriting_route_success_rate" in result.stderr
    assert "missing metric evidence" in result.stderr


def test_model_corpus_script_requires_evidence_metric_values_to_match_manifest(
    tmp_path,
) -> None:
    payload = _manifest(fixture_type="model_backed")
    _write_evidence_artifacts(tmp_path, payload, fixture_type="model_backed")
    visual_evidence = payload["evidence"]["visualEmbedding"]  # type: ignore[index]
    assert isinstance(visual_evidence, dict)
    metrics = _section_metrics(payload, "visualEmbedding")
    metrics["visual_embedding_hit_rate_at_k"] = 0.1
    (tmp_path / visual_evidence["evidencePath"]).write_text(  # type: ignore[index]
        json.dumps(
            _evidence_artifact(
                str(visual_evidence["runId"]),
                fixture_type="model_backed",
                metrics=metrics,
            )
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "visualEmbedding" in result.stderr
    assert "visual_embedding_hit_rate_at_k" in result.stderr
    assert "metric mismatch" in result.stderr


def test_model_corpus_script_requires_aggregate_metric_evidence(tmp_path) -> None:
    payload = _manifest(fixture_type="model_backed")
    _write_evidence_artifacts(
        tmp_path,
        payload,
        fixture_type="model_backed",
        include_aggregate_metrics=False,
    )
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "hybrid_hit_rate_at_k" in result.stderr
    assert "aggregate metric evidence" in result.stderr


def test_model_corpus_script_rejects_conflicting_aggregate_metric_evidence(
    tmp_path,
) -> None:
    payload = _manifest(fixture_type="model_backed")
    _write_evidence_artifacts(tmp_path, payload, fixture_type="model_backed")
    qwen_evidence = payload["evidence"]["qwen"]  # type: ignore[index]
    assert isinstance(qwen_evidence, dict)
    metrics = _section_metrics(payload, "qwen")
    metrics.update(_aggregate_metrics(payload))
    metrics["provenance_truth_rate"] = 0.5
    (tmp_path / qwen_evidence["evidencePath"]).write_text(  # type: ignore[index]
        json.dumps(
            _evidence_artifact(
                str(qwen_evidence["runId"]),
                fixture_type="model_backed",
                metrics=metrics,
            )
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "phase8_5_model_manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_model_corpus.py",
            "--require-model-backed",
            "--manifest",
            str(manifest),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "qwen" in result.stderr
    assert "provenance_truth_rate" in result.stderr
    assert "metric mismatch" in result.stderr


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


def _write_evidence_artifacts(
    tmp_path: Path,
    payload: dict[str, object],
    *,
    fixture_type: str | None = None,
    include_aggregate_metrics: bool = True,
) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence_sections = payload["evidence"]
    assert isinstance(evidence_sections, dict)
    for section, evidence in evidence_sections.items():
        assert isinstance(evidence, dict)
        evidence["evidencePath"] = f"evidence/{section}.json"
        artifact: dict[str, object]
        if fixture_type:
            metrics = _section_metrics(payload, section)
            if include_aggregate_metrics:
                metrics.update(_aggregate_metrics(payload))
            artifact = _evidence_artifact(
                str(evidence["runId"]),
                fixture_type=fixture_type,
                metrics=metrics,
            )
        else:
            artifact = {"runId": evidence["runId"]}
        (evidence_dir / f"{section}.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )


def _evidence_artifact(
    run_id: str,
    *,
    fixture_type: str,
    metrics: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "fixtureType": fixture_type,
        "runId": run_id,
        "runManifest": {
            "run_id": run_id,
            "pipeline_version": PIPELINE_VERSION,
        },
        "metrics": metrics or {"source": "unit-test"},
    }


def _section_metrics(payload: dict[str, object], section: str) -> dict[str, object]:
    metric_names = {
        "qwen": (
            "qwen_handwriting_route_success_rate",
            "qwen_review_required_rate",
        ),
        "granite": (
            "granite_table_structure_score",
            "granite_kvp_exact_match",
        ),
        "textEmbedding": ("text_embedding_hit_rate_at_k",),
        "visualEmbedding": ("visual_embedding_hit_rate_at_k",),
    }[section]
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    return {name: metrics[name] for name in metric_names}


def _aggregate_metrics(payload: dict[str, object]) -> dict[str, object]:
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    return {
        "hybrid_hit_rate_at_k": metrics["hybrid_hit_rate_at_k"],
        "provenance_truth_rate": metrics["provenance_truth_rate"],
    }
