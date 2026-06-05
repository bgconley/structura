from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from lib.config import Settings, get_settings
from lib.db.connection import db_connection
from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
)

_SERVICE_QUEUES = {
    "model-qwen-semantic": "semantic-annotations",
    "model-granite": "extraction",
    "model-embed": "embeddings",
    "model-vl-embed": "visual-embeddings",
}


def configured_model_health_snapshots(
    settings: Settings | None = None,
    *,
    include_queue_metrics: bool = False,
) -> list[dict[str, Any]]:
    resolved = settings or get_settings()
    return [
        _snapshot(
            service_name="model-qwen-semantic",
            mode=resolved.model_mode,
            profile_name=resolved.qwen_semantic_profile,
            endpoint_role="qwen-vl-semantic-smart",
            queue_metrics=_queue_metrics("model-qwen-semantic", include_queue_metrics),
        ),
        _snapshot(
            service_name="model-granite",
            mode=resolved.model_mode,
            profile_name=resolved.granite_profile or GRANITE_VISION_PROFILE,
            endpoint_role="granite-vision",
            queue_metrics=_queue_metrics("model-granite", include_queue_metrics),
        ),
        _snapshot(
            service_name="model-embed",
            mode=resolved.model_mode,
            profile_name=resolved.text_embed_profile or TEXT_EMBED_PROFILE,
            endpoint_role="text-embedding",
            queue_metrics=_queue_metrics("model-embed", include_queue_metrics),
        ),
        _snapshot(
            service_name="model-vl-embed",
            mode=resolved.model_mode,
            profile_name=resolved.visual_embed_profile or VISUAL_EMBED_PROFILE,
            endpoint_role="visual-embedding",
            queue_metrics=_queue_metrics("model-vl-embed", include_queue_metrics),
        ),
    ]


def probed_model_health_snapshots(
    settings: Settings | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 1.0,
    include_queue_metrics: bool = False,
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
        return configured_model_health_snapshots(
            resolved,
            include_queue_metrics=include_queue_metrics,
        )
    return [
        _probe_snapshot(
            service_name=service_name,
            url=url,
            mode=resolved.model_mode,
            profile_name=profile_name,
            endpoint_role=endpoint_role,
            transport=transport,
            timeout_seconds=timeout_seconds,
            queue_metrics=_queue_metrics(service_name, include_queue_metrics),
        )
        for service_name, url, profile_name, endpoint_role in endpoints
    ]


def _snapshot(
    *,
    service_name: str,
    mode: str,
    profile_name: str,
    endpoint_role: str,
    queue_metrics: dict[str, Any],
) -> dict[str, Any]:
    status = "fixture" if mode == "fixture" else "unknown"
    return {
        "service_name": service_name,
        "status": status,
        "metrics_json": _base_metrics(
            mode=mode,
            profile_name=profile_name,
            endpoint_role=endpoint_role,
            queue_metrics=queue_metrics,
        ),
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
    queue_metrics: dict[str, Any],
) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()
    metrics = _base_metrics(
        mode=mode,
        profile_name=profile_name,
        endpoint_role=endpoint_role,
        queue_metrics=queue_metrics,
    )
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


def _base_metrics(
    *,
    mode: str,
    profile_name: str,
    endpoint_role: str,
    queue_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model_mode": mode,
        "profile_name": profile_name,
        "endpoint_role": endpoint_role,
        "payload_redaction": "enabled",
        "last_success_at": queue_metrics.get("last_success_at"),
        "timeout_count": queue_metrics.get("timeout_count", 0),
        "error_count": queue_metrics.get("error_count", 0),
        "queue_depth": queue_metrics.get("queue_depth"),
        "oldest_job_age_seconds": queue_metrics.get("oldest_job_age_seconds"),
    }


def _queue_metrics(service_name: str, include_queue_metrics: bool) -> dict[str, Any]:
    if not include_queue_metrics:
        return {}
    queue_name = _SERVICE_QUEUES.get(service_name)
    if queue_name is None:
        return {}
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      max(finished_at) FILTER (WHERE status = 'succeeded') AS last_success_at,
                      count(*) FILTER (
                        WHERE status IN ('failed', 'dead_letter')
                          AND error_json::text ILIKE '%timeout%'
                      ) AS timeout_count,
                      count(*) FILTER (WHERE status IN ('failed', 'dead_letter')) AS error_count,
                      count(*) FILTER (
                        WHERE status IN ('queued', 'leased', 'running')
                      ) AS queue_depth,
                      extract(epoch FROM (now() - min(scheduled_at) FILTER (
                        WHERE status IN ('queued', 'leased', 'running')
                      ))) AS oldest_job_age_seconds
                    FROM pipeline_jobs
                    WHERE queue_name = %s
                    """,
                    (queue_name,),
                )
                row = cur.fetchone()
    except Exception:
        return {
            "queue_depth": None,
            "oldest_job_age_seconds": None,
        }
    if not row:
        return {
            "queue_depth": 0,
            "oldest_job_age_seconds": None,
        }
    last_success = row.get("last_success_at")
    oldest_age = row.get("oldest_job_age_seconds")
    return {
        "last_success_at": last_success.isoformat() if last_success else None,
        "timeout_count": int(row.get("timeout_count") or 0),
        "error_count": int(row.get("error_count") or 0),
        "queue_depth": int(row.get("queue_depth") or 0),
        "oldest_job_age_seconds": (
            max(0, int(float(oldest_age))) if oldest_age is not None else None
        ),
    }
