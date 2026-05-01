from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from lib.config import Settings, get_settings
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)


def configured_model_health_snapshots(
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    resolved = settings or get_settings()
    return [
        _snapshot(
            service_name="model-qwen-semantic",
            mode=resolved.model_mode,
            profile_name=resolved.qwen_semantic_profile,
            endpoint_role="qwen-vl-semantic-smart",
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


def probed_model_health_snapshots(
    settings: Settings | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 1.0,
) -> list[dict[str, Any]]:
    resolved = settings or get_settings()
    endpoints = [
        (
            "model-qwen-semantic",
            resolved.model_qwen_semantic_url,
            resolved.qwen_semantic_profile,
            "qwen-vl-semantic-smart",
        ),
        (
            "model-granite",
            resolved.model_granite_url,
            resolved.granite_profile or GRANITE_VISION_PROFILE,
            "granite-vision",
        ),
        (
            "model-embed",
            resolved.model_text_embed_url,
            resolved.text_embed_profile or TEXT_EMBED_PROFILE,
            "text-embedding",
        ),
        (
            "model-vl-embed",
            resolved.model_visual_embed_url,
            resolved.visual_embed_profile or VISUAL_EMBED_PROFILE,
            "visual-embedding",
        ),
    ]
    if resolved.model_mode == "fixture":
        return configured_model_health_snapshots(resolved)
    return [
        _probe_snapshot(
            service_name=service_name,
            url=url,
            mode=resolved.model_mode,
            profile_name=profile_name,
            endpoint_role=endpoint_role,
            transport=transport,
            timeout_seconds=timeout_seconds,
        )
        for service_name, url, profile_name, endpoint_role in endpoints
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


def _probe_snapshot(
    *,
    service_name: str,
    url: str,
    mode: str,
    profile_name: str,
    endpoint_role: str,
    transport: httpx.BaseTransport | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()
    metrics: dict[str, Any] = {
        "model_mode": mode,
        "profile_name": profile_name,
        "endpoint_role": endpoint_role,
        "payload_redaction": "enabled",
    }
    try:
        with httpx.Client(
            base_url=url.rstrip("/"),
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        ) as client:
            response = _health_response(client)
        status = "ok" if response.status_code < 300 else "unavailable"
        metrics["http_status"] = response.status_code
    except Exception as exc:
        status = "unavailable"
        metrics["error_class"] = exc.__class__.__name__
    return {
        "service_name": service_name,
        "status": status,
        "metrics_json": metrics,
        "checked_at": checked_at,
    }


def _health_response(client: httpx.Client) -> httpx.Response:
    first = client.get("/healthz")
    if first.status_code < 300:
        return first
    return client.get("/health")
