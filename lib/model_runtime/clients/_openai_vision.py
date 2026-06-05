from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.http_client import ModelHttpClient, ModelProtocolError
from lib.model_runtime.profiles import ModelProfile


class OpenAIVisionGenerateClient:
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

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        if request.profile_name != self.profile.name:
            raise ModelProtocolError("Vision request profile does not match client profile.")
        start = time.monotonic()
        input_hashes = _validated_input_hashes(request)
        structured_output_requested = request.response_json_schema is not None
        structured_output_used = structured_output_requested
        fallback_reason: str | None = None
        payload = _openai_payload(
            request=request,
            profile=self.profile,
            use_structured_output=structured_output_requested,
        )
        try:
            response = self._http.post_json(
                "/v1/chat/completions",
                payload,
                timeout_seconds=request.timeout_seconds,
            )
        except ModelProtocolError as exc:
            if not structured_output_requested or not request.allow_structured_output_fallback:
                raise
            fallback_reason = str(exc)
            structured_output_used = False
            payload = _openai_payload(
                request=request,
                profile=self.profile,
                use_structured_output=False,
            )
            response = self._http.post_json(
                "/v1/chat/completions",
                payload,
                timeout_seconds=request.timeout_seconds,
            )
        raw_text, finish_reason = _raw_message_content(response)
        normalized, confidence = _structured_content(raw_text)
        return VisionGenerateResponse(
            profile_name=self.profile.name,
            model_name=str(response.get("model") or self.profile.base_model),
            model_version=str(
                response.get("model_version") or response.get("system_fingerprint") or ""
            ),
            source_engine=self.profile.source_engine,
            prompt_version=request.prompt_version,
            raw_text=raw_text,
            normalized_json=normalized,
            confidence_json=confidence,
            input_sha256=input_hashes,
            latency_ms=max(0, int((time.monotonic() - start) * 1000)),
            finish_reason=finish_reason,
            usage_json=_usage_json(response),
            structured_output_used=structured_output_used,
            structured_output_fallback_reason=fallback_reason,
        )


def _validated_input_hashes(request: VisionGenerateRequest) -> tuple[str, ...]:
    if not request.image_inputs:
        raise ModelProtocolError("Vision model request requires at least one image input.")
    if len(request.image_inputs) > 4:
        raise ModelProtocolError("Vision model request has too many image inputs.")
    hashes: list[str] = []
    for image in request.image_inputs:
        try:
            hashes.append(image.validated_sha256())
        except ValueError as exc:
            raise ModelProtocolError(str(exc)) from exc
    return tuple(hashes)


def _openai_payload(
    *,
    request: VisionGenerateRequest,
    profile: ModelProfile,
    use_structured_output: bool,
) -> dict[str, Any]:
    content: list[dict[str, object]] = [{"type": "text", "text": request.prompt}]
    for image in request.image_inputs:
        if not image.mime_type.startswith("image/"):
            raise ModelProtocolError("Vision model image input must have an image MIME type.")
        data_url = base64.b64encode(image.content).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image.mime_type};base64,{data_url}"},
            }
        )
    payload: dict[str, Any] = {
        "model": profile.base_model,
        "messages": [{"role": "user", "content": content}],
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
    if use_structured_output and request.response_json_schema is not None:
        schema_name = request.response_schema_name or "structured_response"
        if request.structured_output_mode == "response_format_json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": request.response_json_schema,
                    "strict": True,
                },
            }
        elif request.structured_output_mode == "structured_outputs_json":
            payload["structured_outputs"] = {"json": request.response_json_schema}
        else:
            raise ModelProtocolError(
                f"Unsupported structured output mode: {request.structured_output_mode}"
            )
    else:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _raw_message_content(response: dict[str, Any]) -> tuple[str, str | None]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelProtocolError("Vision model response is missing choices.")
    first = choices[0]
    if not isinstance(first, dict):
        raise ModelProtocolError("Vision model response choice must be an object.")
    finish_reason = first.get("finish_reason")
    if finish_reason == "length":
        raise ModelProtocolError(
            "Vision model response was truncated before valid JSON completed.",
            details={
                "finish_reason": "length",
                "usage": _usage_json(response),
                "model": response.get("model"),
                "model_version": response.get("model_version")
                or response.get("system_fingerprint"),
            },
        )
    message = first.get("message")
    if not isinstance(message, dict):
        raise ModelProtocolError("Vision model response choice is missing message.")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content, str(finish_reason) if finish_reason else None
    raise ModelProtocolError("Vision model response message content is empty.")


def _usage_json(response: dict[str, Any]) -> dict[str, object]:
    usage = response.get("usage")
    return dict(usage) if isinstance(usage, dict) else {}


def _structured_content(raw_text: str) -> tuple[dict[str, object], dict[str, object]]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ModelProtocolError("Vision model content is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ModelProtocolError("Vision model JSON content must be an object.")
    confidence = parsed.get("confidence")
    if not isinstance(confidence, dict):
        confidence = {}
    normalized = parsed.get("normalized")
    if isinstance(normalized, dict):
        return normalized, confidence
    direct_payload = dict(parsed)
    direct_payload.pop("confidence", None)
    if direct_payload:
        return direct_payload, confidence
    return {}, confidence
