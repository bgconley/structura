from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx


class ModelRuntimeError(Exception):
    retryable = False


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
        request_path = _validated_relative_path(path)
        try:
            response = self._client.post(
                request_path,
                json=payload,
                timeout=timeout_seconds or self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeoutError("Model service timed out.") from exc
        except httpx.HTTPError as exc:
            raise ModelServiceError("Model service request failed.") from exc

        if 300 <= response.status_code < 400:
            raise ModelProtocolError("Model service returned a redirect.")
        if response.status_code >= 500:
            raise ModelServiceError(f"Model service returned HTTP {response.status_code}.")
        if response.status_code >= 400:
            raise ModelProtocolError(f"Model service returned HTTP {response.status_code}.")
        if len(response.content) > self.max_response_bytes:
            raise ModelProtocolError("Model service response is too large.")
        try:
            parsed = response.json()
        except ValueError as exc:
            raise ModelProtocolError("Model service returned invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ModelProtocolError("Model service JSON response must be an object.")
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
