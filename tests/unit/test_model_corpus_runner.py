from __future__ import annotations

import json

import pytest

from scripts.run_model_corpus import evaluate_model_corpus_manifest


def test_model_corpus_runner_requires_model_backed_evidence_when_requested() -> None:
    payload = _manifest(fixture_type="deterministic_fixture")

    with pytest.raises(SystemExit, match="model-backed"):
        evaluate_model_corpus_manifest(payload, require_model_backed=True)


def test_model_corpus_runner_enforces_required_sections_and_thresholds() -> None:
    payload = _manifest(fixture_type="model_backed")
    result = evaluate_model_corpus_manifest(payload, require_model_backed=True)

    assert result["fixtureType"] == "model_backed"
    assert result["metrics"]["provenance_truth_rate"] == 1.0

    payload["metrics"]["visual_embedding_hit_rate_at_k"] = 0.2
    with pytest.raises(SystemExit, match="visual_embedding_hit_rate_at_k"):
        evaluate_model_corpus_manifest(payload, require_model_backed=True)


def test_model_corpus_example_manifest_is_valid() -> None:
    payload = json.loads(
        open("tests/fixtures/model_corpus/phase8_5_model_manifest.example.json").read()
    )

    result = evaluate_model_corpus_manifest(payload, require_model_backed=False)

    assert result["fixtureType"] == "deterministic_fixture"


def _manifest(*, fixture_type: str) -> dict[str, object]:
    return {
        "fixtureType": fixture_type,
        "evidence": {
            "qwen": {"profile": "qwen3-vl-8b-instruct-nvfp4-local:v1"},
            "granite": {"profile": "granite-4.0-3b-vision-bf16:v1"},
            "textEmbedding": {"profile": "qwen3-embedding-4b-1536:v1"},
            "visualEmbedding": {"profile": "qwen3-vl-embedding-2b-1024:v1"},
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
    }
