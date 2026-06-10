from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

from lib.model_runtime.redaction import redact_model_payload


class ModelRuntimeError(Exception):
    retryable = False

    def __init__(
        self,
        message: str = "",
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.details = dict(details or {})


class ModelConfigurationError(ModelRuntimeError):
    pass


class ModelProtocolError(ModelRuntimeError):
    pass


class ModelTimeoutError(ModelRuntimeError):
    retryable = True


class ModelServiceError(ModelRuntimeError):
    retryable = True


class ModelHttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 60.0,
        max_response_bytes: int = 1024 * 1024,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = _validated_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        parsed = self.post_json_value(path, payload, timeout_seconds=timeout_seconds)
        if not isinstance(parsed, dict):
            raise ModelProtocolError(
                "Model service JSON response must be an object.",
                details=_safe_request_details(path, payload),
            )
        return parsed

    def post_json_value(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any] | list[Any]:
        request_path = _validated_relative_path(path)
        try:
            response = self._client.post(
                request_path,
                json=payload,
                timeout=timeout_seconds or self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError(
                "Model service timed out.",
                details=_safe_request_details(request_path, payload),
            ) from exc
        except httpx.HTTPError as exc:
            raise ModelServiceError(
                "Model service request failed.",
                details=_safe_request_details(request_path, payload),
            ) from exc

        if 300 <= response.status_code < 400:
            raise ModelProtocolError(
                "Model service returned a redirect.",
                details=_safe_response_details(request_path, payload, response),
            )
        if response.status_code >= 500:
            raise ModelServiceError(
                f"Model service returned HTTP {response.status_code}.",
                details=_safe_response_details(request_path, payload, response),
            )
        if response.status_code >= 400:
            raise ModelProtocolError(
                f"Model service returned HTTP {response.status_code}.",
                details=_safe_response_details(request_path, payload, response),
            )
        if len(response.content) > self.max_response_bytes:
            raise ModelProtocolError(
                "Model service response is too large.",
                details=_safe_response_details(request_path, payload, response),
            )
        try:
            parsed = response.json()
        except ValueError as exc:
            raise ModelProtocolError(
                "Model service returned invalid JSON.",
                details=_safe_response_details(request_path, payload, response),
            ) from exc
        if not isinstance(parsed, dict | list):
            raise ModelProtocolError(
                "Model service JSON response must be an object or array.",
                details=_safe_response_details(request_path, payload, response),
            )
        return parsed


def _validated_base_url(base_url: str) -> str:
    if not base_url:
        raise ModelConfigurationError("Model service base URL is required.")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ModelConfigurationError("Model service base URL must use http or https.")
    if not parsed.netloc:
        raise ModelConfigurationError("Model service base URL must include a host.")
    return base_url.rstrip("/")


def _validated_relative_path(path: str) -> str:
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        raise ModelProtocolError("Model service request path must be relative.")
    if not path.startswith("/"):
        raise ModelProtocolError("Model service request path must start with '/'.")
    return path


def _safe_request_details(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": path,
        "request": redact_model_payload(payload),
    }


def _safe_response_details(
    path: str,
    payload: dict[str, Any],
    response: httpx.Response,
) -> dict[str, Any]:
    details = _safe_request_details(path, payload)
    details["http_status"] = response.status_code
    try:
        parsed = response.json()
    except ValueError:
        return details
    details["response"] = redact_model_payload(parsed)
    return details
