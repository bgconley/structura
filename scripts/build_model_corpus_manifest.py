from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.model_runtime.model_corpus_evidence import (  # noqa: E402
    AGGREGATE_EVIDENCE_METRICS,
    EVIDENCE_SECTION_METRICS,
    MANIFEST_RUN_PROFILE_KEYS,
    REQUIRED_EVIDENCE_SECTIONS,
    evidence_artifact_measured_at,
    evidence_artifact_profiles,
    evidence_artifact_run_id,
    evidence_metric_number,
    load_evidence_artifact,
)
from lib.model_runtime.model_corpus_manifest import (  # noqa: E402
    REQUIRED_METRICS,
    evaluate_model_corpus_manifest,
)


def main() -> int:
    args = _parse_args()
    payload = build_model_corpus_manifest(
        run_id=args.run_id,
        model_mode=args.model_mode,
        evidence_paths={
            "qwen": args.qwen_evidence,
            "granite": args.granite_evidence,
            "textEmbedding": args.text_embedding_evidence,
            "visualEmbedding": args.visual_embedding_evidence,
        },
        thresholds=_load_json_object(args.thresholds_json, label="thresholds"),
        gold_metrics=_load_json_object(args.gold_metrics_json, label="gold metrics"),
        gold_thresholds=_load_json_object(args.gold_thresholds_json, label="gold thresholds"),
    )
    evaluate_model_corpus_manifest(
        payload,
        require_model_backed=True,
        manifest_path=args.output,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a Phase 8.5 model-backed release manifest from explicit "
            "measured evidence artifacts."
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model-mode", choices=("live", "required"), required=True)
    parser.add_argument("--qwen-evidence", type=Path, required=True)
    parser.add_argument("--granite-evidence", type=Path, required=True)
    parser.add_argument("--text-embedding-evidence", type=Path, required=True)
    parser.add_argument("--visual-embedding-evidence", type=Path, required=True)
    parser.add_argument("--thresholds-json", type=Path, required=True)
    parser.add_argument("--gold-metrics-json", type=Path, required=True)
    parser.add_argument("--gold-thresholds-json", type=Path, required=True)
    return parser.parse_args()


def build_model_corpus_manifest(
    *,
    run_id: str,
    model_mode: str,
    evidence_paths: dict[str, Path],
    thresholds: dict[str, Any],
    gold_metrics: dict[str, Any],
    gold_thresholds: dict[str, Any],
) -> dict[str, Any]:
    artifacts = {
        section: load_evidence_artifact(section, evidence_paths[section].expanduser())
        for section in REQUIRED_EVIDENCE_SECTIONS
    }
    evidence = {
        section: _evidence_section(section, artifacts[section], evidence_paths[section])
        for section in REQUIRED_EVIDENCE_SECTIONS
    }
    metrics = _manifest_metrics(artifacts)
    return {
        "fixtureType": "model_backed",
        "runId": run_id,
        "runManifest": {
            "model_mode": model_mode,
            **{
                run_manifest_key: evidence[section]["profile"]
                for section, run_manifest_key in MANIFEST_RUN_PROFILE_KEYS.items()
            },
        },
        "evidence": evidence,
        "metrics": metrics,
        "thresholds": thresholds,
        "goldMetrics": gold_metrics,
        "goldThresholds": gold_thresholds,
    }


def _evidence_section(
    section: str,
    artifact: dict[str, Any],
    path: Path,
) -> dict[str, str]:
    run_id = evidence_artifact_run_id(artifact)
    if not isinstance(run_id, str) or not run_id.strip():
        raise SystemExit(f"Model corpus evidence {section} artifact is missing runId metadata.")
    measured_at = evidence_artifact_measured_at(artifact)
    if not isinstance(measured_at, str) or not measured_at.strip():
        raise SystemExit(
            f"Model corpus evidence {section} artifact is missing measuredAt metadata."
        )
    profiles = evidence_artifact_profiles(section, artifact)
    if not profiles:
        raise SystemExit(f"Model corpus evidence {section} artifact is missing profile metadata.")
    profile = profiles[0]
    for artifact_profile in profiles:
        if artifact_profile != profile:
            raise SystemExit(
                f"Model corpus evidence {section} artifact profile mismatch: "
                f"{artifact_profile} != {profile}."
            )
    return {
        "profile": profile,
        "runId": run_id,
        "measuredAt": measured_at,
        "evidencePath": str(path.expanduser().resolve()),
    }


def _manifest_metrics(artifacts: dict[str, dict[str, Any]]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for section, metric_names in EVIDENCE_SECTION_METRICS.items():
        artifact_metrics = _artifact_metrics(section, artifacts[section])
        for metric in metric_names:
            metrics[metric] = _required_artifact_metric(section, artifact_metrics, metric)
    for metric in AGGREGATE_EVIDENCE_METRICS:
        metrics[metric] = _aggregate_metric(artifacts, metric)
    missing = [metric for metric in REQUIRED_METRICS if metric not in metrics]
    if missing:
        raise SystemExit(f"Model corpus manifest metrics missing: {', '.join(missing)}")
    return metrics


def _artifact_metrics(section: str, artifact: dict[str, Any]) -> dict[str, Any]:
    metrics = artifact.get("metrics")
    if not isinstance(metrics, dict):
        raise SystemExit(f"Model corpus evidence {section} artifact is missing metrics.")
    return metrics


def _required_artifact_metric(
    section: str,
    metrics: dict[str, Any],
    metric: str,
) -> float:
    if metric not in metrics:
        raise SystemExit(
            f"Model corpus evidence {section} artifact missing metric evidence {metric}."
        )
    return evidence_metric_number(metrics[metric], section=section, metric=metric)


def _aggregate_metric(artifacts: dict[str, dict[str, Any]], metric: str) -> float:
    value: float | None = None
    for section, artifact in artifacts.items():
        artifact_metrics = artifact.get("metrics")
        if not isinstance(artifact_metrics, dict) or metric not in artifact_metrics:
            continue
        actual = evidence_metric_number(artifact_metrics[metric], section=section, metric=metric)
        if value is None:
            value = actual
        elif abs(actual - value) > 1e-9:
            raise SystemExit(
                f"Model corpus evidence {section} aggregate metric mismatch for {metric}: "
                f"{actual:.4f} != {value:.4f}"
            )
    if value is None:
        raise SystemExit(f"Model corpus aggregate metric evidence missing {metric}.")
    return value


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Model corpus {label} JSON is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Model corpus {label} JSON must be an object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
