from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = Path("tests/fixtures/model_corpus/phase8_5_model_manifest.example.json")

REQUIRED_EVIDENCE_SECTIONS = ("qwen", "granite", "textEmbedding", "visualEmbedding")
REQUIRED_METRICS = (
    "qwen_handwriting_route_success_rate",
    "qwen_review_required_rate",
    "granite_table_structure_score",
    "granite_kvp_exact_match",
    "text_embedding_hit_rate_at_k",
    "visual_embedding_hit_rate_at_k",
    "hybrid_hit_rate_at_k",
    "provenance_truth_rate",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Structura Phase 8.5 model corpus gate.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-model-backed", action="store_true")
    args = parser.parse_args()

    payload = _load_manifest(args.manifest)
    result = evaluate_model_corpus_manifest(
        payload,
        require_model_backed=args.require_model_backed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def evaluate_model_corpus_manifest(
    payload: dict[str, Any],
    *,
    require_model_backed: bool,
) -> dict[str, Any]:
    fixture_type = str(payload.get("fixtureType") or "")
    if require_model_backed and fixture_type != "model_backed":
        raise SystemExit("Model corpus manifest is not model-backed.")
    evidence = _required_mapping(payload, "evidence")
    for section in REQUIRED_EVIDENCE_SECTIONS:
        if section not in evidence or not isinstance(evidence[section], dict):
            raise SystemExit(f"Model corpus evidence section missing: {section}")
    metrics = _required_mapping(payload, "metrics")
    thresholds = _required_mapping(payload, "thresholds")
    for metric in REQUIRED_METRICS:
        _assert_metric(metrics, thresholds, metric)
    return {
        "fixtureType": fixture_type,
        "metrics": {metric: float(metrics[metric]) for metric in REQUIRED_METRICS},
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Model corpus manifest not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Model corpus manifest must be a JSON object.")
    return payload


def _required_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise SystemExit(f"Model corpus manifest must include object: {key}")
    return value


def _assert_metric(metrics: dict[str, Any], thresholds: dict[str, Any], metric: str) -> None:
    if metric not in metrics:
        raise SystemExit(f"Model corpus metric missing: {metric}")
    if metric not in thresholds:
        raise SystemExit(f"Model corpus threshold missing: {metric}")
    actual = float(metrics[metric])
    expected = float(thresholds[metric])
    if actual < expected:
        raise SystemExit(f"Model corpus {metric} {actual:.4f} is below {expected:.4f}.")


if __name__ == "__main__":
    raise SystemExit(main())
