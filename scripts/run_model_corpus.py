from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    from lib.model_runtime.reliability_gold_metrics import (
        assert_gold_corpus_metrics_pass,
        evaluate_gold_corpus_metrics,
    )
    from lib.model_runtime.reliability_report import build_phase85_run_manifest

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
    gold_metrics = _required_mapping(payload, "goldMetrics")
    gold_thresholds = _required_mapping(payload, "goldThresholds")
    gold_summary = evaluate_gold_corpus_metrics(gold_metrics, gold_thresholds)
    assert_gold_corpus_metrics_pass(gold_summary)
    run_id = str(payload.get("runId") or payload.get("run_id") or "phase85-manifest")
    manifest_overrides = payload.get("runManifest")
    if manifest_overrides is not None and not isinstance(manifest_overrides, dict):
        raise SystemExit("Model corpus runManifest must be an object when provided.")
    return {
        "fixtureType": fixture_type,
        "runManifest": build_phase85_run_manifest(
            run_id=run_id,
            overrides=manifest_overrides,
        ),
        "metrics": {metric: float(metrics[metric]) for metric in REQUIRED_METRICS},
        "goldCorpusMetrics": gold_summary,
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
