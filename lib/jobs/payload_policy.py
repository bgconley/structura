from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from lib.config import get_settings
from lib.jobs.errors import JobServiceError, PayloadSafetyError
from lib.jobs.models import QueueTransportProfile

SENSITIVE_PAYLOAD_KEYS = {
    "document_text",
    "raw_document_text",
    "raw_text",
    "raw_model_output",
    "model_output",
    "prompt",
    "prompt_body",
    "sensitive_fields",
    "extracted_sensitive_fields",
}

SUPPORTED_QUEUE_TRANSPORTS = {"pgmq", "pipeline_jobs", "redis"}


def queue_transport_profile(requested: str | None = None) -> QueueTransportProfile:
    transport = (requested or get_settings().queue_transport).lower()
    if transport not in SUPPORTED_QUEUE_TRANSPORTS:
        supported = ", ".join(sorted(SUPPORTED_QUEUE_TRANSPORTS))
        raise JobServiceError(f"Unsupported queue transport '{transport}'. Supported: {supported}.")
    if transport == "pgmq":
        return QueueTransportProfile(
            requested=transport,
            active="pipeline_jobs",
            reason=(
                "PGMQ is the preferred transport, but Phase 0 uses the Postgres job "
                "ledger directly because the pinned ParadeDB PG17 image does not package PGMQ."
            ),
        )
    if transport == "redis":
        return QueueTransportProfile(
            requested=transport,
            active="pipeline_jobs",
            reason=(
                "Redis remains a fallback profile; Phase 0 keeps pipeline_jobs as durable truth."
            ),
        )
    return QueueTransportProfile(requested=transport, active="pipeline_jobs")


def retry_delay_seconds(
    attempt_count: int,
    *,
    base_seconds: int = 30,
    cap_seconds: int = 3600,
) -> int:
    exponent = max(attempt_count - 1, 0)
    return int(min(cap_seconds, base_seconds * (2**exponent)))


def sanitize_job_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    def walk(value: Any, path: tuple[str, ...]) -> Any:
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for key, child in value.items():
                normalized = str(key).lower()
                if normalized in SENSITIVE_PAYLOAD_KEYS:
                    raise PayloadSafetyError(
                        f"Job payload key {'.'.join((*path, str(key)))} is not allowed."
                    )
                sanitized[str(key)] = walk(child, (*path, str(key)))
            return sanitized
        if isinstance(value, list):
            return [walk(item, path) for item in value]
        return value

    return cast(dict[str, Any], walk(dict(payload), ()))
