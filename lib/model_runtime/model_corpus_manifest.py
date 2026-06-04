from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from lib.model_runtime.model_corpus_evidence import (
    MANIFEST_RUN_PROFILE_KEYS,
    MODEL_BACKED_RUN_MODES,
    REQUIRED_EVIDENCE_SECTIONS,
    assert_aggregate_metric_evidence,
    assert_model_backed_evidence,
    evidence_summary,
)

VALID_FIXTURE_TYPES = frozenset({"deterministic_fixture", "model_backed"})
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


def fixture_type(payload: dict[str, Any]) -> str:
    value = payload.get("fixtureType")
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(
            "Model corpus manifest fixtureType must be deterministic_fixture or model_backed."
        )
    normalized = value.strip()
    if normalized not in VALID_FIXTURE_TYPES:
        raise SystemExit(
            "Model corpus manifest fixtureType must be deterministic_fixture or model_backed."
        )
    return normalized


def manifest_number(value: Any, *, kind: str, metric: str) -> float:
    if isinstance(value, bool):
        raise SystemExit(f"Model corpus {kind} {metric} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Model corpus {kind} {metric} must be numeric.") from exc
    if not math.isfinite(number):
        raise SystemExit(f"Model corpus {kind} {metric} must be finite.")
    if number < 0 or number > 1:
        raise SystemExit(f"Model corpus {kind} {metric} must be between 0 and 1.")
    return number


def evaluate_model_corpus_manifest(
    payload: dict[str, Any],
    *,
    require_model_backed: bool,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    from lib.model_runtime.profiles import (
        GRANITE_VISION_PROFILE,
        QWEN_SEMANTIC_PROFILE,
        TEXT_EMBED_PROFILE,
        VISUAL_EMBED_PROFILE,
    )
    from lib.model_runtime.reliability_gold_metrics import (
        assert_gold_corpus_metrics_pass,
        evaluate_gold_corpus_metrics,
    )
    from lib.model_runtime.reliability_report import build_phase85_run_manifest

    corpus_fixture_type = fixture_type(payload)
    if require_model_backed and corpus_fixture_type != "model_backed":
        raise SystemExit("Model corpus manifest is not model-backed.")
    manifest_overrides = payload.get("runManifest")
    if manifest_overrides is not None and not isinstance(manifest_overrides, dict):
        raise SystemExit("Model corpus runManifest must be an object when provided.")
    if corpus_fixture_type == "model_backed":
        _assert_model_backed_manifest_run_mode(manifest_overrides)
    evidence = _required_mapping(payload, "evidence")
    metrics = _required_mapping(payload, "metrics")
    model_backed_artifacts: dict[str, dict[str, Any]] = {}
    for section in REQUIRED_EVIDENCE_SECTIONS:
        if section not in evidence or not isinstance(evidence[section], dict):
            raise SystemExit(f"Model corpus evidence section missing: {section}")
        if corpus_fixture_type == "model_backed":
            artifact = assert_model_backed_evidence(
                section,
                evidence[section],
                metrics=metrics,
                manifest_path=manifest_path,
            )
            if artifact is not None:
                model_backed_artifacts[section] = artifact
    if model_backed_artifacts:
        assert_aggregate_metric_evidence(model_backed_artifacts, metrics)
    thresholds = _required_mapping(payload, "thresholds")
    for metric in REQUIRED_METRICS:
        _assert_metric(metrics, thresholds, metric)
    gold_metrics = _required_mapping(payload, "goldMetrics")
    gold_thresholds = _required_mapping(payload, "goldThresholds")
    gold_summary = evaluate_gold_corpus_metrics(gold_metrics, gold_thresholds)
    assert_gold_corpus_metrics_pass(gold_summary)
    run_id = str(payload.get("runId") or payload.get("run_id") or "phase85-manifest")
    run_manifest = build_phase85_run_manifest(
        run_id=run_id,
        overrides=manifest_overrides,
    )
    if corpus_fixture_type == "model_backed":
        _assert_model_backed_evidence_profiles(
            evidence,
            expected_profiles={
                "qwen": QWEN_SEMANTIC_PROFILE,
                "granite": GRANITE_VISION_PROFILE,
                "textEmbedding": TEXT_EMBED_PROFILE,
                "visualEmbedding": VISUAL_EMBED_PROFILE,
            },
        )
        _assert_model_backed_manifest_profiles(evidence, run_manifest)
    return {
        "fixtureType": corpus_fixture_type,
        "evidence": {
            section: evidence_summary(evidence[section]) for section in REQUIRED_EVIDENCE_SECTIONS
        },
        "runManifest": run_manifest,
        "metrics": {
            metric: manifest_number(metrics[metric], kind="metric", metric=metric)
            for metric in REQUIRED_METRICS
        },
        "goldCorpusMetrics": gold_summary,
    }


def load_manifest(path: Path) -> dict[str, Any]:
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


def _assert_model_backed_manifest_run_mode(run_manifest: Any) -> None:
    if not isinstance(run_manifest, dict):
        raise SystemExit("Model corpus model-backed manifest must include runManifest.model_mode.")
    mode = run_manifest.get("model_mode") or run_manifest.get("modelMode")
    if not isinstance(mode, str) or not mode.strip():
        raise SystemExit("Model corpus model-backed manifest must include runManifest.model_mode.")
    normalized_mode = mode.strip()
    if normalized_mode not in MODEL_BACKED_RUN_MODES:
        raise SystemExit(
            "Model corpus model-backed manifest runManifest.model_mode must be "
            f"live or required; got {normalized_mode!r}."
        )


def _assert_model_backed_evidence_profiles(
    evidence: dict[str, Any],
    *,
    expected_profiles: dict[str, str],
) -> None:
    for section, expected_profile in expected_profiles.items():
        value = evidence[section].get("profile")
        actual_profile = value.strip() if isinstance(value, str) else ""
        if actual_profile != expected_profile:
            raise SystemExit(
                f"Model corpus evidence {section} profile must be {expected_profile}; "
                f"got {actual_profile!r}."
            )


def _assert_model_backed_manifest_profiles(
    evidence: dict[str, Any],
    run_manifest: dict[str, Any],
) -> None:
    for section, run_manifest_key in MANIFEST_RUN_PROFILE_KEYS.items():
        expected_profile = str(evidence[section]["profile"]).strip()
        actual_profile = run_manifest.get(run_manifest_key)
        if not isinstance(actual_profile, str) or not actual_profile.strip():
            raise SystemExit(
                f"Model corpus model-backed manifest must include runManifest.{run_manifest_key}."
            )
        normalized_profile = actual_profile.strip()
        if normalized_profile != expected_profile:
            raise SystemExit(
                f"Model corpus model-backed manifest {run_manifest_key} "
                f"profile mismatch: {normalized_profile} != {expected_profile}."
            )


def _assert_metric(metrics: dict[str, Any], thresholds: dict[str, Any], metric: str) -> None:
    if metric not in metrics:
        raise SystemExit(f"Model corpus metric missing: {metric}")
    if metric not in thresholds:
        raise SystemExit(f"Model corpus threshold missing: {metric}")
    actual = manifest_number(metrics[metric], kind="metric", metric=metric)
    expected = manifest_number(thresholds[metric], kind="threshold", metric=metric)
    if actual < expected:
        raise SystemExit(f"Model corpus {metric} {actual:.4f} is below {expected:.4f}.")
