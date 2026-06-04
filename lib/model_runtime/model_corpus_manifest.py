from __future__ import annotations

import math
from pathlib import Path
from typing import Any

VALID_FIXTURE_TYPES = frozenset({"deterministic_fixture", "model_backed"})
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
