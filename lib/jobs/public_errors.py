"""Privacy-safe job failures shared by persistence and public read models.

Exception text is untrusted document/model content. Never derive a public
message from it, including when reading historical error rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

PUBLIC_MESSAGES = {
    "job_cancelled": "Document processing was cancelled.",
    "worker_lease_expired": (
        "The processing worker stopped responding. The job will be retried if attempts remain."
    ),
    "processing_failed": "Document processing failed. Retry or contact an administrator.",
    "model_timeout": "The document model did not respond in time. Please retry.",
    "model_unavailable": "The document model is unavailable. Please retry later.",
    "model_response_invalid": "The document model returned an unusable response. Please retry.",
    "source_unavailable": "A required document asset could not be read. Contact an administrator.",
    "storage_unavailable": "Document storage is unavailable. Please retry later.",
    "database_unavailable": "Document data could not be saved. Please retry later.",
}

_CLASS_CODES = {
    "JobCancelled": "job_cancelled",
    "WorkerLeaseExpired": "worker_lease_expired",
    "ModelTimeoutError": "model_timeout",
    "TimeoutError": "model_timeout",
    "ModelUnavailableError": "model_unavailable",
    "ModelProtocolError": "model_response_invalid",
    "FileNotFoundError": "source_unavailable",
    "PermissionError": "storage_unavailable",
    "OperationalError": "database_unavailable",
    "InterfaceError": "database_unavailable",
}

# Deliberately small machine diagnostics: arbitrary keys and string values can
# themselves contain source text. Raw tracebacks/prompts/exceptions are omitted.
_COUNT_KEYS = {"attempt_count", "status_code", "response_status", "response_bytes"}
_POLICY_VALUES = {"fail", "continue", "required", "live", "fixture", "review_only"}


def safe_job_failure(
    error_class: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the only failure payload written by the lifecycle repository.

    ``message`` is accepted for existing worker call compatibility, but is never
    retained. An opaque reference allows operators to correlate safe records.
    """
    del message
    code = _CLASS_CODES.get(error_class, "processing_failed")
    safe_class = error_class if error_class in _CLASS_CODES else "ProcessingError"
    return {
        "error_id": str(uuid4()),
        "public_code": code,
        "error_class": safe_class,
        "message": PUBLIC_MESSAGES[code],
        "last_error": PUBLIC_MESSAGES[code],
        "details": _safe_diagnostics(details),
    }


def public_job_error(error: object) -> str | None:
    """Project safe text even for legacy rows containing raw exceptions."""
    if not isinstance(error, Mapping) or not error:
        return None
    code = error.get("public_code")
    message = (
        PUBLIC_MESSAGES.get(code, PUBLIC_MESSAGES["processing_failed"])
        if isinstance(code, str)
        else PUBLIC_MESSAGES["processing_failed"]
    )
    reference = error.get("error_id")
    try:
        parsed = UUID(reference) if isinstance(reference, str) else None
    except ValueError:
        parsed = None
    return f"{message} Reference: {parsed}." if parsed else message


def _safe_diagnostics(details: Mapping[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    safe: dict[str, Any] = {}
    for key in _COUNT_KEYS:
        value = details.get(key)
        if type(value) is int and 0 <= value <= 2**31 - 1:
            safe[key] = value
    policy = details.get("model_failure_policy")
    if isinstance(policy, str) and policy in _POLICY_VALUES:
        safe["model_failure_policy"] = policy
    return safe
