from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.model_runtime.http_client import ModelTimeoutError


@dataclass(frozen=True)
class ExtractionFailurePolicy:
    retryable: bool
    policy: str


def extraction_failure_policy(
    *,
    payload: dict[str, Any],
    exc: Exception,
) -> ExtractionFailurePolicy:
    route_profile = str(payload.get("route_profile") or "")
    if isinstance(exc, ModelTimeoutError) and route_profile == "docling_plus_granite_structured":
        return ExtractionFailurePolicy(
            retryable=False,
            policy="do_not_retry_timeout",
        )
    return ExtractionFailurePolicy(
        retryable=True,
        policy="default_retryable",
    )
