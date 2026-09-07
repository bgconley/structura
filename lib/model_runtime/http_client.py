from __future__ import annotations

import json
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
        api_key: str | None = None,
    ) -> None:
        self.base_url = _validated_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        if api_key is not None and (
            not api_key or any(ord(c) < 33 or ord(c) > 126 for c in api_key)
        ):
            raise ModelConfigurationError("Model authentication token is invalid.")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
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
            with self._client.stream(
                "POST",
                request_path,
                json=payload,
                timeout=timeout_seconds or self.timeout_seconds,
            ) as response:
                details = _safe_request_details(request_path, payload)
                details["http_status"] = response.status_code
                if 300 <= response.status_code < 400:
                    raise ModelProtocolError("Model service returned a redirect.", details=details)
                if response.status_code >= 500 or response.status_code == 429:
                    raise ModelServiceError(
                        f"Model service returned HTTP {response.status_code}.", details=details
                    )
                if response.status_code >= 400:
                    raise ModelProtocolError(
                        f"Model service returned HTTP {response.status_code}.", details=details
                    )
                # Read decoded bytes incrementally, also bounding compressed responses.
                content = bytearray()
                for chunk in response.iter_bytes(
                    chunk_size=min(65536, self.max_response_bytes + 1)
                ):
                    if len(content) + len(chunk) > self.max_response_bytes:
                        raise ModelProtocolError(
                            "Model service response is too large.", details=details
                        )
                    content.extend(chunk)
        except httpx.TimeoutException:
            raise ModelTimeoutError(
                "Model service timed out.", details=_safe_request_details(request_path, payload)
            ) from None
        except httpx.HTTPError:
            raise ModelServiceError(
                "Model service request failed.",
                details=_safe_request_details(request_path, payload),
            ) from None
        try:
            parsed = json.loads(content)
        except (ValueError, UnicodeDecodeError):
            raise ModelProtocolError(
                "Model service returned invalid JSON.",
                details=_safe_request_details(request_path, payload),
            ) from None

        if not isinstance(parsed, dict | list):
            raise ModelProtocolError(
                "Model service JSON response must be an object or array.",
                details=_safe_request_details(request_path, payload),
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
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ModelConfigurationError("Model service credentials must not be in its URL.")
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
