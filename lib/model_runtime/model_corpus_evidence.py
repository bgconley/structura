from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.model_runtime.model_corpus_report_statuses import assert_model_corpus_report_statuses_pass

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
MANIFEST_RUN_PROFILE_KEYS = {
    "qwen": "semantic_profile",
    "granite": "granite_profile",
    "textEmbedding": "text_embedding_profile",
    "visualEmbedding": "visual_embedding_profile",
}
MODEL_BACKED_RUN_MODES = frozenset({"live", "required"})
REQUIRED_EVIDENCE_ARTIFACT_PAYLOAD_KEYS = (
    "acceptanceGates",
    "checks",
    "documents",
    "metrics",
)
MODEL_BACKED_ARTIFACT_FIXTURE_TYPE = "model_backed"
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


def evidence_metric_number(
    value: Any,
    *,
    section: str,
    metric: str,
    path: Path | None = None,
) -> float:
    suffix = f": {path}" if path is not None else "."
    if isinstance(value, bool):
        raise SystemExit(f"Model corpus evidence {section} metric {metric} must be numeric{suffix}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            f"Model corpus evidence {section} metric {metric} must be numeric{suffix}"
        ) from exc
    if not math.isfinite(number):
        raise SystemExit(f"Model corpus evidence {section} metric {metric} must be finite{suffix}")
    if number < 0 or number > 1:
        raise SystemExit(
            f"Model corpus evidence {section} metric {metric} must be between 0 and 1{suffix}"
        )
    return number


def assert_model_backed_evidence(
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
    measured_at = parse_evidence_measured_at(section, str(evidence["measuredAt"]))
    if manifest_path is None:
        return None
    evidence_path = resolve_evidence_path(str(evidence["evidencePath"]), manifest_path)
    if not evidence_path.is_file():
        raise SystemExit(f"Model corpus evidence {section} evidencePath not found: {evidence_path}")
    evidence_artifact = load_evidence_artifact(section, evidence_path)
    artifact_run_id = evidence_artifact_run_id(evidence_artifact)
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
    assert_evidence_artifact_measured_at(
        section,
        evidence_artifact,
        measured_at=measured_at,
        path=evidence_path,
    )
    assert_evidence_artifact_lineage(section, evidence_artifact, evidence_path)
    assert_evidence_artifact_model_mode(section, evidence_artifact, evidence_path)
    assert_evidence_artifact_profile(section, evidence, evidence_artifact, evidence_path)
    assert_evidence_artifact_metrics(section, evidence_artifact, metrics, evidence_path)
    return evidence_artifact


def evidence_summary(evidence: dict[str, Any]) -> dict[str, str]:
    summary: dict[str, str] = {}
    for key in REQUIRED_MODEL_BACKED_EVIDENCE_KEYS:
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            summary[key] = value
    return summary


def resolve_evidence_path(evidence_path: str, manifest_path: Path) -> Path:
    path = Path(evidence_path).expanduser()
    if path.is_absolute():
        return path
    return manifest_path.parent / path


def load_evidence_artifact(section: str, path: Path) -> dict[str, Any]:
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


def evidence_artifact_run_id(artifact: dict[str, Any]) -> Any:
    run_id = artifact.get("runId") or artifact.get("run_id")
    if run_id is not None:
        return run_id
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if isinstance(run_manifest, dict):
        return run_manifest.get("run_id") or run_manifest.get("runId")
    return None


def assert_evidence_artifact_measured_at(
    section: str,
    artifact: dict[str, Any],
    *,
    measured_at: datetime,
    path: Path,
) -> None:
    artifact_measured_at = evidence_artifact_measured_at(artifact)
    if artifact_measured_at is None:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include measuredAt metadata: {path}"
        )
    parsed = parse_evidence_measured_at(section, str(artifact_measured_at), path=path)
    if parsed != measured_at:
        raise SystemExit(
            f"Model corpus evidence {section} measuredAt mismatch: "
            f"{parsed.isoformat()} != {measured_at.isoformat()}"
        )


def evidence_artifact_measured_at(artifact: dict[str, Any]) -> Any:
    measured_at = artifact.get("measuredAt") or artifact.get("measured_at")
    if measured_at is not None:
        return measured_at
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if isinstance(run_manifest, dict):
        return run_manifest.get("measuredAt") or run_manifest.get("measured_at")
    return None


def assert_evidence_artifact_lineage(
    section: str,
    artifact: dict[str, Any],
    path: Path,
) -> None:
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if not isinstance(run_manifest, dict):
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include "
            f"report evidence runManifest: {path}"
        )
    if artifact.get("fixtureType") != MODEL_BACKED_ARTIFACT_FIXTURE_TYPE:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath fixtureType must be "
            f"{MODEL_BACKED_ARTIFACT_FIXTURE_TYPE}: {path}"
        )
    pipeline_version = run_manifest.get("pipeline_version") or run_manifest.get("pipelineVersion")
    if pipeline_version != expected_pipeline_version():
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath has unexpected "
            f"pipeline_version {pipeline_version!r}: {path}"
        )
    if not any(key in artifact for key in REQUIRED_EVIDENCE_ARTIFACT_PAYLOAD_KEYS):
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include report evidence: {path}"
        )
    assert_model_corpus_report_statuses_pass(section, artifact, path)


def assert_evidence_artifact_profile(
    section: str,
    evidence: dict[str, Any],
    artifact: dict[str, Any],
    path: Path,
) -> None:
    expected_profile = str(evidence["profile"])
    artifact_profiles = evidence_artifact_profiles(section, artifact)
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


def evidence_artifact_profiles(section: str, artifact: dict[str, Any]) -> list[str]:
    profiles: list[str] = []
    for key in EVIDENCE_ARTIFACT_PROFILE_KEYS:
        _append_profile(profiles, artifact.get(key))
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if isinstance(run_manifest, dict):
        for key in EVIDENCE_ARTIFACT_RUN_MANIFEST_PROFILE_KEYS[section]:
            _append_profile(profiles, run_manifest.get(key))
    return profiles


def assert_evidence_artifact_model_mode(
    section: str,
    artifact: dict[str, Any],
    path: Path,
) -> None:
    run_manifest = artifact.get("runManifest") or artifact.get("run_manifest")
    if not isinstance(run_manifest, dict):
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include "
            f"report evidence runManifest: {path}"
        )
    mode = run_manifest.get("model_mode") or run_manifest.get("modelMode")
    if not isinstance(mode, str) or not mode.strip():
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath must include "
            f"runManifest.model_mode metadata: {path}"
        )
    normalized_mode = mode.strip()
    if normalized_mode not in MODEL_BACKED_RUN_MODES:
        raise SystemExit(
            f"Model corpus evidence {section} runManifest.model_mode must be live or required; "
            f"got {normalized_mode!r}: {path}"
        )


def assert_evidence_artifact_metrics(
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
        actual = evidence_metric_number(
            artifact_metrics[metric], section=section, metric=metric, path=path
        )
        expected = evidence_metric_number(
            metrics[metric], section=section, metric=metric, path=path
        )
        if abs(actual - expected) > 1e-9:
            raise SystemExit(
                f"Model corpus evidence {section} metric mismatch for {metric}: "
                f"{actual:.4f} != {expected:.4f}"
            )


def assert_aggregate_metric_evidence(
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
            actual = evidence_metric_number(
                artifact_metrics[metric], section=section, metric=metric
            )
            expected = evidence_metric_number(metrics[metric], section=section, metric=metric)
            if abs(actual - expected) > 1e-9:
                raise SystemExit(
                    f"Model corpus evidence {section} metric mismatch for {metric}: "
                    f"{actual:.4f} != {expected:.4f}"
                )
        if not seen:
            raise SystemExit(f"Model corpus aggregate metric evidence missing {metric}.")


def parse_evidence_measured_at(
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


def expected_pipeline_version() -> str:
    from lib.model_runtime.reliability_report import PIPELINE_VERSION

    return PIPELINE_VERSION


def _append_profile(profiles: list[str], value: Any) -> None:
    if isinstance(value, str) and value.strip():
        profiles.append(value.strip())
