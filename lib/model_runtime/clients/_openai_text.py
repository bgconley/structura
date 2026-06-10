from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx

from lib.model_runtime.clients._openai_vision import (
    _raw_message_content,
    _response_format_schema_name,
    _usage_json,
    _validate_structured_content,
)
from lib.model_runtime.contracts import TextGenerateRequest, TextGenerateResponse
from lib.model_runtime.http_client import ModelHttpClient, ModelProtocolError
from lib.model_runtime.profiles import ModelProfile


class OpenAITextGenerateClient:
    """Text-only structured chat against an OpenAI-compatible endpoint.

    Shares the strict response_format/json_schema policy and fail-closed
    response handling with the vision client; the only difference is the
    absence of image content parts.
    """

    def __init__(
        self,
        *,
        profile: ModelProfile,
        http_client_base_url: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.profile = profile
        self._http = ModelHttpClient(
            base_url=http_client_base_url,
            timeout_seconds=60,
            transport=transport,
        )

    def generate(self, request: TextGenerateRequest) -> TextGenerateResponse:
        if request.profile_name != self.profile.name:
            raise ModelProtocolError("Text request profile does not match client profile.")
        if request.response_json_schema is None:
            raise ModelProtocolError(
                f"Text profile {self.profile.name} requires a JSON Schema for "
                "structured generation."
            )
        start = time.monotonic()
        payload = _openai_text_payload(request=request, profile=self.profile)
        response = self._http.post_json(
            "/v1/chat/completions",
            payload,
            timeout_seconds=request.timeout_seconds,
        )
        raw_text, finish_reason = _raw_message_content(response)
        normalized = _structured_text_content(
            raw_text,
            response_schema=request.response_json_schema,
            response_schema_name=request.response_schema_name,
        )
        return TextGenerateResponse(
            profile_name=self.profile.name,
            model_name=str(response.get("model") or self.profile.base_model),
            model_version=str(
                response.get("model_version") or response.get("system_fingerprint") or ""
            ),
            source_engine=self.profile.source_engine,
            prompt_version=request.prompt_version,
            raw_text=raw_text,
            normalized_json=normalized,
            prompt_sha256=hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
            latency_ms=max(0, int((time.monotonic() - start) * 1000)),
            finish_reason=finish_reason,
            usage_json=_usage_json(response),
            structured_output_used=True,
        )


def _openai_text_payload(
    *,
    request: TextGenerateRequest,
    profile: ModelProfile,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": profile.base_model,
        "messages": [{"role": "user", "content": request.prompt}],
        "max_tokens": request.max_output_tokens,
        "temperature": request.temperature,
        "metadata": {
            "profile_name": request.profile_name,
            "prompt_version": request.prompt_version,
            "response_schema_name": request.response_schema_name,
        },
    }
    if request.seed is not None:
        payload["seed"] = request.seed
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": _response_format_schema_name(request.response_schema_name),
            "schema": request.response_json_schema,
            "strict": True,
        },
    }
    return payload


def _structured_text_content(
    raw_text: str,
    *,
    response_schema: dict[str, Any],
    response_schema_name: str | None,
) -> dict[str, object]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ModelProtocolError("Text model content is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ModelProtocolError("Text model JSON content must be an object.")
    _validate_structured_content(
        parsed,
        response_schema=response_schema,
        response_schema_name=response_schema_name,
    )
    return dict(parsed)
