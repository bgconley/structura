from __future__ import annotations

from lib.model_runtime.http_client import ModelProtocolError


def is_retryable_semantic_generation_error(exc: Exception) -> bool:
    if isinstance(exc, ModelProtocolError) and _is_structured_output_generation_error(exc):
        return True
    message = str(exc).lower()
    return any(
        fragment in message
        for fragment in (
            "truncated",
            "not valid json",
            "schema validation",
            "semantic annotation output",
            "invalid semantic annotation output",
        )
    )


def _is_structured_output_generation_error(exc: ModelProtocolError) -> bool:
    message = str(exc).lower()
    if message in {
        "vision model content is not valid json.",
        "vision model json content must be an object.",
        "vision model json content does not match response schema.",
        "vision model response message content is empty.",
    }:
        return True
    return "validator" in exc.details and "path" in exc.details
