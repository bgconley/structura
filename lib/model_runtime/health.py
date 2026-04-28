from __future__ import annotations

from typing import Any

from lib.config import Settings, get_settings
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_VL_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)


def configured_model_health_snapshots(
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    resolved = settings or get_settings()
    return [
        _snapshot(
            service_name="model-qwen",
            mode=resolved.model_mode,
            profile_name=resolved.qwen_profile or QWEN_VL_PROFILE,
            endpoint_role="qwen-vl",
        ),
        _snapshot(
            service_name="model-granite",
            mode=resolved.model_mode,
            profile_name=resolved.granite_profile or GRANITE_VISION_PROFILE,
            endpoint_role="granite-vision",
        ),
        _snapshot(
            service_name="model-embed",
            mode=resolved.model_mode,
            profile_name=resolved.text_embed_profile or TEXT_EMBED_PROFILE,
            endpoint_role="text-embedding",
        ),
        _snapshot(
            service_name="model-vl-embed",
            mode=resolved.model_mode,
            profile_name=resolved.visual_embed_profile or VISUAL_EMBED_PROFILE,
            endpoint_role="visual-embedding",
        ),
    ]


def _snapshot(
    *,
    service_name: str,
    mode: str,
    profile_name: str,
    endpoint_role: str,
) -> dict[str, Any]:
    status = "fixture" if mode == "fixture" else "unknown"
    return {
        "service_name": service_name,
        "status": status,
        "metrics_json": {
            "model_mode": mode,
            "profile_name": profile_name,
            "endpoint_role": endpoint_role,
            "payload_redaction": "enabled",
        },
        "checked_at": None,
    }
