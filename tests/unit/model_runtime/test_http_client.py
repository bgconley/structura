from __future__ import annotations

import httpx
import pytest

from lib.model_runtime.http_client import (
    ModelConfigurationError,
    ModelHttpClient,
    ModelProtocolError,
    ModelServiceError,
    ModelTimeoutError,
)
from lib.model_runtime.redaction import redact_model_payload


def test_model_http_client_rejects_missing_or_non_http_base_url() -> None:
    with pytest.raises(ModelConfigurationError, match="base URL"):
        ModelHttpClient(base_url="")

    with pytest.raises(ModelConfigurationError, match="http"):
        ModelHttpClient(base_url="file:///srv/structura/models")


def test_model_http_client_rejects_absolute_request_paths() -> None:
    client = ModelHttpClient(
        base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"ok": True})),
    )

    with pytest.raises(ModelProtocolError, match="relative"):
        client.post_json("http://169.254.169.254/latest/meta-data", {"prompt": "nope"})


def test_model_http_client_rejects_redirects_instead_of_following_them() -> None:
    client = ModelHttpClient(
        base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        ),
    )

    with pytest.raises(ModelProtocolError, match="redirect"):
        client.post_json("/v1/chat/completions", {"messages": []})


def test_model_http_client_maps_timeout_and_service_errors() -> None:
    timeout_client = ModelHttpClient(
        base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(
            lambda _request: (_ for _ in ()).throw(httpx.ReadTimeout("slow model"))
        ),
    )
    with pytest.raises(ModelTimeoutError):
        timeout_client.post_json("/v1/chat/completions", {"messages": []})

    service_client = ModelHttpClient(
        base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(lambda _request: httpx.Response(503, json={"error": "busy"})),
    )
    with pytest.raises(ModelServiceError) as exc_info:
        service_client.post_json("/v1/chat/completions", {"messages": []})
    assert exc_info.value.retryable is True


def test_model_http_client_returns_json_and_rejects_oversized_or_invalid_json() -> None:
    ok_client = ModelHttpClient(
        base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"status": "ok"})),
    )
    assert ok_client.post_json("/health", {}) == {"status": "ok"}

    invalid_client = ModelHttpClient(
        base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text="not-json")),
    )
    with pytest.raises(ModelProtocolError, match="JSON"):
        invalid_client.post_json("/health", {})

    oversized_client = ModelHttpClient(
        base_url="http://model-qwen-semantic:8104",
        max_response_bytes=4,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"status": "ok"})),
    )
    with pytest.raises(ModelProtocolError, match="too large"):
        oversized_client.post_json("/health", {})


def test_redact_model_payload_removes_private_model_inputs_and_outputs() -> None:
    redacted = redact_model_payload(
        {
            "prompt": "show diagnosis details",
            "raw_text": "patient owes $42",
            "image_path": "/srv/structura/tmp/model-inputs/secret.png",
            "objectUri": "filesystem://canonical/sha256/aa/bb/hash/source.pdf",
            "url": "data:image/png;base64,abc",
            "safe": {"status": "timeout"},
        }
    )

    assert redacted["prompt"] == "[redacted]"
    assert redacted["raw_text"] == "[redacted]"
    assert redacted["image_path"] == "[redacted]"
    assert redacted["objectUri"] == "[redacted]"
    assert redacted["url"] == "[redacted]"
    assert redacted["safe"] == {"status": "timeout"}
