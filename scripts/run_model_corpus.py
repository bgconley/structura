from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_MANIFEST = Path("tests/fixtures/model_corpus/phase8_5_model_manifest.example.json")

REQUIRED_EVIDENCE_SECTIONS = ("qwen", "granite", "textEmbedding", "visualEmbedding")
REQUIRED_MODEL_BACKED_EVIDENCE_KEYS = ("profile", "runId", "measuredAt", "evidencePath")
EVIDENCE_ARTIFACT_PROFILE_KEYS = (
    "profile",
    "profileName",
    "profile_name",
    "modelProfile",
    "model_profile",
)
EVIDENCE_ARTIFACT_RUN_MANIFEST_PROFILE_KEYS = {
    "qwen": ("semantic_profile", "qwen_semantic_profile"),
    "granite": ("granite_profile",),
    "textEmbedding": ("text_embedding_profile", "text_embed_profile"),
    "visualEmbedding": ("visual_embedding_profile", "visual_embed_profile"),
}
EVIDENCE_ARTIFACT_MODEL_MODE_KEYS = ("model_mode", "modelMode")
MODEL_BACKED_ARTIFACT_MODES = frozenset({"live", "required"})
REQUIRED_EVIDENCE_ARTIFACT_PAYLOAD_KEYS = (
    "acceptanceGates",
    "checks",
    "documents",
    "metrics",
)
EVIDENCE_SECTION_METRICS = {
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
}
AGGREGATE_EVIDENCE_METRICS = (
    "hybrid_hit_rate_at_k",
    "provenance_truth_rate",
)
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
        manifest_path=args.manifest,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def evaluate_model_corpus_manifest(
    payload: dict[str, Any],
    *,
    require_model_backed: bool,
    manifest_path: Path | None = None,
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
    metrics = _required_mapping(payload, "metrics")
    model_backed_artifacts: dict[str, dict[str, Any]] = {}
    for section in REQUIRED_EVIDENCE_SECTIONS:
        if section not in evidence or not isinstance(evidence[section], dict):
            raise SystemExit(f"Model corpus evidence section missing: {section}")
        if fixture_type == "model_backed":
            artifact = _assert_model_backed_evidence(
                section,
                evidence[section],
                metrics=metrics,
                manifest_path=manifest_path,
            )
            if artifact is not None:
                model_backed_artifacts[section] = artifact
    if model_backed_artifacts:
        _assert_aggregate_metric_evidence(model_backed_artifacts, metrics)
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
        "evidence": {
            section: _evidence_summary(evidence[section]) for section in REQUIRED_EVIDENCE_SECTIONS
        },
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


def _assert_model_backed_evidence(
    section: str,
    evidence: dict[str, Any],
    *,
    metrics: dict[str, Any],
    manifest_path: Path | None,
) -> dict[str, Any] | None:
    for key in REQUIRED_MODEL_BACKED_EVIDENCE_KEYS:
        value = evidence.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(f"Model corpus evidence {section} missing traceable {key}.")
    measured_at = _parse_measured_at(section, str(evidence["measuredAt"]))
    if manifest_path is None:
        return None
    evidence_path = _resolve_evidence_path(str(evidence["evidencePath"]), manifest_path)
    if not evidence_path.is_file():
        raise SystemExit(f"Model corpus evidence {section} evidencePath not found: {evidence_path}")
    evidence_artifact = _load_evidence_artifact(section, evidence_path)
    artifact_run_id = _evidence_artifact_run_id(evidence_artifact)
    if artifact_run_id is None:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include runId metadata: "
            f"{evidence_path}"
        )
    if str(artifact_run_id) != str(evidence["runId"]):
        raise SystemExit(
            f"Model corpus evidence {section} runId mismatch: "
            f"{artifact_run_id} != {evidence['runId']}"
        )
    _assert_evidence_artifact_measured_at(
        section,
        evidence_artifact,
        measured_at=measured_at,
        path=evidence_path,
    )
    _assert_evidence_artifact_lineage(section, evidence_artifact, evidence_path)
    _assert_evidence_artifact_model_mode(section, evidence_artifact, evidence_path)
    _assert_evidence_artifact_profile(section, evidence, evidence_artifact, evidence_path)
    _assert_evidence_artifact_metrics(section, evidence_artifact, metrics, evidence_path)
    return evidence_artifact


def _evidence_summary(evidence: dict[str, Any]) -> dict[str, str]:
    summary: dict[str, str] = {}
    for key in REQUIRED_MODEL_BACKED_EVIDENCE_KEYS:
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            summary[key] = value
    return summary


def _resolve_evidence_path(evidence_path: str, manifest_path: Path) -> Path:
    path = Path(evidence_path).expanduser()
    if path.is_absolute():
        return path
    return manifest_path.parent / path


def _load_evidence_artifact(section: str, path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must contain a JSON object: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must contain a JSON object: {path}"
        )
    return payload


def _evidence_artifact_run_id(artifact: dict[str, Any]) -> Any:
    run_id = artifact.get("runId") or artifact.get("run_id")
    if run_id is not None:
        return run_id
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if isinstance(run_manifest, dict):
        return run_manifest.get("run_id") or run_manifest.get("runId")
    return None


def _assert_evidence_artifact_measured_at(
    section: str,
    artifact: dict[str, Any],
    *,
    measured_at: datetime,
    path: Path,
) -> None:
    artifact_measured_at = _evidence_artifact_measured_at(artifact)
    if artifact_measured_at is None:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include measuredAt metadata: {path}"
        )
    parsed = _parse_measured_at(section, str(artifact_measured_at), path=path)
    if parsed != measured_at:
        raise SystemExit(
            f"Model corpus evidence {section} measuredAt mismatch: "
            f"{parsed.isoformat()} != {measured_at.isoformat()}"
        )


def _evidence_artifact_measured_at(artifact: dict[str, Any]) -> Any:
    measured_at = artifact.get("measuredAt") or artifact.get("measured_at")
    if measured_at is not None:
        return measured_at
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if isinstance(run_manifest, dict):
        return run_manifest.get("measuredAt") or run_manifest.get("measured_at")
    return None


def _assert_evidence_artifact_lineage(
    section: str,
    artifact: dict[str, Any],
    path: Path,
) -> None:
    if artifact.get("fixtureType") == "deterministic_fixture":
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must not be fixture-backed: {path}"
        )

    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if not isinstance(run_manifest, dict):
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include "
            f"report evidence runManifest: {path}"
        )
    pipeline_version = run_manifest.get("pipeline_version") or run_manifest.get("pipelineVersion")
    if pipeline_version != _expected_pipeline_version():
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath has unexpected "
            f"pipeline_version {pipeline_version!r}: {path}"
        )
    if not any(key in artifact for key in REQUIRED_EVIDENCE_ARTIFACT_PAYLOAD_KEYS):
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include report evidence: {path}"
        )


def _assert_evidence_artifact_profile(
    section: str,
    evidence: dict[str, Any],
    artifact: dict[str, Any],
    path: Path,
) -> None:
    expected_profile = str(evidence["profile"])
    artifact_profiles = _evidence_artifact_profiles(section, artifact)
    if not artifact_profiles:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include profile metadata: {path}"
        )
    for artifact_profile in artifact_profiles:
        if artifact_profile != expected_profile:
            raise SystemExit(
                f"Model corpus evidence {section} profile mismatch: "
                f"{artifact_profile} != {expected_profile}"
            )


def _evidence_artifact_profiles(section: str, artifact: dict[str, Any]) -> list[str]:
    profiles: list[str] = []
    for key in EVIDENCE_ARTIFACT_PROFILE_KEYS:
        _append_profile(profiles, artifact.get(key))
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if isinstance(run_manifest, dict):
        for key in EVIDENCE_ARTIFACT_RUN_MANIFEST_PROFILE_KEYS[section]:
            _append_profile(profiles, run_manifest.get(key))
    return profiles


def _append_profile(profiles: list[str], value: Any) -> None:
    if isinstance(value, str) and value.strip():
        profiles.append(value.strip())


def _assert_evidence_artifact_model_mode(
    section: str,
    artifact: dict[str, Any],
    path: Path,
) -> None:
    modes = _evidence_artifact_model_modes(artifact)
    if not modes:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include model_mode metadata: {path}"
        )
    for mode in modes:
        if mode not in MODEL_BACKED_ARTIFACT_MODES:
            raise SystemExit(
                f"Model corpus evidence {section} model_mode must be live or required; "
                f"got {mode!r}: {path}"
            )


def _evidence_artifact_model_modes(artifact: dict[str, Any]) -> list[str]:
    modes: list[str] = []
    for key in EVIDENCE_ARTIFACT_MODEL_MODE_KEYS:
        _append_model_mode(modes, artifact.get(key))
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if isinstance(run_manifest, dict):
        for key in EVIDENCE_ARTIFACT_MODEL_MODE_KEYS:
            _append_model_mode(modes, run_manifest.get(key))
    return modes


def _append_model_mode(modes: list[str], value: Any) -> None:
    if isinstance(value, str) and value.strip():
        modes.append(value.strip())


def _assert_evidence_artifact_metrics(
    section: str,
    artifact: dict[str, Any],
    metrics: dict[str, Any],
    path: Path,
) -> None:
    artifact_metrics = artifact.get("metrics")
    if not isinstance(artifact_metrics, dict):
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include metric evidence: {path}"
        )
    for metric in EVIDENCE_SECTION_METRICS[section]:
        if metric not in artifact_metrics:
            raise SystemExit(
                f"Model corpus evidence {section} evidencePath missing metric evidence "
                f"{metric}: {path}"
            )
        actual = _metric_float(artifact_metrics[metric], section=section, metric=metric, path=path)
        expected = _metric_float(metrics[metric], section=section, metric=metric, path=path)
        if abs(actual - expected) > 1e-9:
            raise SystemExit(
                f"Model corpus evidence {section} metric mismatch for {metric}: "
                f"{actual:.4f} != {expected:.4f}"
            )


def _assert_aggregate_metric_evidence(
    artifacts: dict[str, dict[str, Any]],
    metrics: dict[str, Any],
) -> None:
    for metric in AGGREGATE_EVIDENCE_METRICS:
        seen = False
        for section, artifact in artifacts.items():
            artifact_metrics = artifact.get("metrics")
            if not isinstance(artifact_metrics, dict) or metric not in artifact_metrics:
                continue
            seen = True
            actual = _metric_float(artifact_metrics[metric], section=section, metric=metric)
            expected = _metric_float(metrics[metric], section=section, metric=metric)
            if abs(actual - expected) > 1e-9:
                raise SystemExit(
                    f"Model corpus evidence {section} metric mismatch for {metric}: "
                    f"{actual:.4f} != {expected:.4f}"
                )
        if not seen:
            raise SystemExit(f"Model corpus aggregate metric evidence missing {metric}.")


def _metric_float(
    value: Any,
    *,
    section: str,
    metric: str,
    path: Path | None = None,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        suffix = f": {path}" if path is not None else "."
        raise SystemExit(
            f"Model corpus evidence {section} metric {metric} must be numeric{suffix}"
        ) from exc


def _parse_measured_at(
    section: str,
    value: str,
    *,
    path: Path | None = None,
) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        suffix = f": {path}" if path is not None else "."
        raise SystemExit(
            f"Model corpus evidence {section} measuredAt must be ISO-8601{suffix}"
        ) from exc
    if parsed.tzinfo is None:
        suffix = f": {path}" if path is not None else "."
        raise SystemExit(
            f"Model corpus evidence {section} measuredAt must include timezone{suffix}"
        )
    return parsed


def _expected_pipeline_version() -> str:
    from lib.model_runtime.reliability_report import PIPELINE_VERSION

    return PIPELINE_VERSION


if __name__ == "__main__":
    raise SystemExit(main())
