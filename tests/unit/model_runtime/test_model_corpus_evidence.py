from __future__ import annotations

from pathlib import Path

import pytest

from lib.model_runtime.model_corpus_evidence import (
    evidence_artifact_measured_at,
    evidence_artifact_profiles,
    evidence_artifact_run_id,
    evidence_metric_number,
)


def test_evidence_artifact_helpers_are_public_runtime_contract() -> None:
    artifact = {
        "runManifest": {
            "run_id": "phase85-qwen-run",
            "measuredAt": "2026-06-04T12:00:00+00:00",
            "semantic_profile": "qwen3-vl-8b-fp8-semantic:v1",
        }
    }

    assert evidence_artifact_run_id(artifact) == "phase85-qwen-run"
    assert evidence_artifact_measured_at(artifact) == "2026-06-04T12:00:00+00:00"
    assert evidence_artifact_profiles("qwen", artifact) == ["qwen3-vl-8b-fp8-semantic:v1"]


def test_evidence_metric_number_requires_real_bounded_numeric_value() -> None:
    path = Path("evidence/qwen.json")

    assert (
        evidence_metric_number(
            0.9,
            section="qwen",
            metric="qwen_handwriting_route_success_rate",
            path=path,
        )
        == 0.9
    )

    with pytest.raises(
        SystemExit, match="qwen.*qwen_handwriting_route_success_rate must be numeric"
    ):
        evidence_metric_number(
            False,
            section="qwen",
            metric="qwen_handwriting_route_success_rate",
            path=path,
        )

    with pytest.raises(SystemExit, match="granite.*granite_table_structure_score must be finite"):
        evidence_metric_number(
            float("inf"),
            section="granite",
            metric="granite_table_structure_score",
            path=path,
        )

    with pytest.raises(SystemExit, match="visualEmbedding.*visual_embedding_hit_rate_at_k"):
        evidence_metric_number(
            -0.1,
            section="visualEmbedding",
            metric="visual_embedding_hit_rate_at_k",
            path=path,
        )
