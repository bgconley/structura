from __future__ import annotations

from importlib import metadata
from typing import Any

from lib.config.settings import get_settings
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    QWEN_VISION_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
    get_model_profile,
)
from lib.model_runtime.reliability_report_normalization import json_safe
from lib.model_runtime.reliability_versions import (
    CANDIDATE_GATE_VERSION,
    CONTRACT_REGISTRY_VERSION,
    GRANITE_PROMPT_VERSION,
    PIPELINE_VERSION,
    PLANNER_VERSION,
    RECONCILER_VERSION,
    REGION_ENVELOPE_VERSION,
    SMART_PROMPT_VERSION,
    VISUAL_INPUT_PLAN_VERSION,
)


def build_phase85_run_manifest(
    *,
    run_id: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    granite = get_model_profile(GRANITE_VISION_PROFILE)
    vision_fallback_provider = "qwen" if settings.qwen_vision_fallback_enabled else "granite"
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "pipeline_version": PIPELINE_VERSION,
        "model_mode": settings.model_mode,
        "docling_version": _docling_version(),
        "semantic_profile": QWEN_SEMANTIC_PROFILE,
        "semantic_prompt_version": SMART_PROMPT_VERSION,
        "granite_profile": GRANITE_VISION_PROFILE,
        "granite_model": granite.base_model,
        "granite_prompt_version": GRANITE_PROMPT_VERSION,
        "vision_fallback_provider": vision_fallback_provider,
        "qwen_vision_fallback_enabled": settings.qwen_vision_fallback_enabled,
        "text_embedding_profile": TEXT_EMBED_PROFILE,
        "visual_embedding_profile": VISUAL_EMBED_PROFILE,
        "planner_version": PLANNER_VERSION,
        "contract_registry_version": CONTRACT_REGISTRY_VERSION,
        "region_envelope_version": REGION_ENVELOPE_VERSION,
        "candidate_gate_version": CANDIDATE_GATE_VERSION,
        "reconciler_version": RECONCILER_VERSION,
        "visual_input_plan_version": VISUAL_INPUT_PLAN_VERSION,
        "decoding": {
            "temperature": 0,
            "top_p": None,
            "seed": 0,
        },
    }
    if settings.qwen_vision_fallback_enabled:
        manifest["qwen_vision_profile"] = settings.qwen_vision_profile or QWEN_VISION_PROFILE
    if overrides:
        manifest.update(json_safe(overrides))
        manifest["run_id"] = run_id
    return manifest


def _docling_version() -> str:
    try:
        return metadata.version("docling")
    except metadata.PackageNotFoundError:
        return "worker-docling-isolated"
