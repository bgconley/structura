from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.model_runtime.http_client import ModelRuntimeError


@dataclass(frozen=True)
class ExtractionFailurePolicy:
    retryable: bool
    policy: str


def model_exception_retryable(exc: Exception, *, default: bool = True) -> bool:
    """Derive retryability from the model runtime exception contract.

    ModelRuntimeError subclasses declare it explicitly: timeouts and service
    errors are transient (retryable), while protocol and configuration errors
    are deterministic (non-retryable). Non-model exceptions fall back to the
    caller-provided default.
    """
    if isinstance(exc, ModelRuntimeError):
        return bool(getattr(exc, "retryable", default))
    return default


def extraction_failure_policy(
    *,
    payload: dict[str, Any],
    exc: Exception,
) -> ExtractionFailurePolicy:
    del payload  # Retryability is route-independent; timeouts retry on all routes.
    if isinstance(exc, ModelRuntimeError):
        if model_exception_retryable(exc):
            return ExtractionFailurePolicy(
                retryable=True,
                policy="retryable_model_exception",
            )
        return ExtractionFailurePolicy(
            retryable=False,
            policy="non_retryable_model_exception",
        )
    return ExtractionFailurePolicy(
        retryable=True,
        policy="default_retryable",
    )
