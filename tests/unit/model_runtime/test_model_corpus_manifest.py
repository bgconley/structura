from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.model_runtime.model_corpus_manifest import (
    evaluate_model_corpus_manifest,
    fixture_type,
    manifest_number,
)


def test_fixture_type_requires_known_manifest_lineage() -> None:
    assert fixture_type({"fixtureType": " deterministic_fixture "}) == "deterministic_fixture"
    assert fixture_type({"fixtureType": "model_backed"}) == "model_backed"

    with pytest.raises(SystemExit, match="fixtureType.*deterministic_fixture.*model_backed"):
        fixture_type({})

    with pytest.raises(SystemExit, match="fixtureType.*deterministic_fixture.*model_backed"):
        fixture_type({"fixtureType": "legacy_fixture"})


def test_manifest_number_requires_real_bounded_numeric_value() -> None:
    assert manifest_number(0.75, kind="metric", metric="hybrid_hit_rate_at_k") == 0.75

    with pytest.raises(SystemExit, match="metric hybrid_hit_rate_at_k must be numeric"):
        manifest_number(True, kind="metric", metric="hybrid_hit_rate_at_k")

    with pytest.raises(SystemExit, match="threshold granite_table_structure_score must be finite"):
        manifest_number(float("nan"), kind="threshold", metric="granite_table_structure_score")

    with pytest.raises(
        SystemExit, match="metric visual_embedding_hit_rate_at_k must be between 0 and 1"
    ):
        manifest_number(1.2, kind="metric", metric="visual_embedding_hit_rate_at_k")


def test_evaluate_model_corpus_manifest_is_owned_by_model_runtime() -> None:
    payload = json.loads(
        Path("tests/fixtures/model_corpus/phase8_5_model_manifest.example.json").read_text(
            encoding="utf-8"
        )
    )

    result = evaluate_model_corpus_manifest(payload, require_model_backed=False)

    assert result["fixtureType"] == "deterministic_fixture"
    assert result["runManifest"]["pipeline_version"] == "phase8_5_reliability_v1"
    assert result["metrics"]["visual_embedding_hit_rate_at_k"] == 1.0
