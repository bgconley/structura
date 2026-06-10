from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.http_client import ModelHttpClient, ModelProtocolError
from lib.model_runtime.profiles import ModelProfile

_RESPONSE_FORMAT_NAME_MAX_LENGTH = 64
_RESPONSE_FORMAT_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


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
        input_hashes = _validated_input_hashes(request, profile=self.profile)
        if request.response_json_schema is None:
            raise ModelProtocolError(
                f"Vision profile {self.profile.name} requires a JSON Schema for "
                "structured generation."
            )
        payload = _openai_payload(
            request=request,
            profile=self.profile,
        )
        response = self._http.post_json(
            "/v1/chat/completions",
            payload,
            timeout_seconds=request.timeout_seconds,
        )
        raw_text, finish_reason = _raw_message_content(response)
        normalized, confidence = _structured_content(
            raw_text,
            response_schema=request.response_json_schema,
            response_schema_name=request.response_schema_name,
        )
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
            structured_output_used=True,
        )


def _validated_input_hashes(
    request: VisionGenerateRequest,
    *,
    profile: ModelProfile,
) -> tuple[str, ...]:
    if not request.image_inputs:
        raise ModelProtocolError("Vision model request requires at least one image input.")
    max_images = profile.max_images_per_request or 4
    if len(request.image_inputs) > max_images:
        raise ModelProtocolError("Vision model request has too many image inputs.")
    hashes: list[str] = []
    for image in request.image_inputs:
        if profile.max_image_bytes is not None and len(image.content) > profile.max_image_bytes:
            raise ModelProtocolError("Vision model image input exceeds profile byte limit.")
        try:
            hashes.append(image.validated_sha256())
        except ValueError as exc:
            raise ModelProtocolError(str(exc)) from exc
    return tuple(hashes)


def _openai_payload(
    *,
    request: VisionGenerateRequest,
    profile: ModelProfile,
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
    schema_name = _response_format_schema_name(request.response_schema_name)
    payload["response_format"] = {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "schema": request.response_json_schema,
            "strict": True,
        },
    }
    return payload


def _response_format_schema_name(name: str | None) -> str:
    raw_name = str(name or "").strip() or "structured_response"
    sanitized = _RESPONSE_FORMAT_NAME_PATTERN.sub("_", raw_name)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_-") or "structured_response"
    if len(sanitized) <= _RESPONSE_FORMAT_NAME_MAX_LENGTH:
        return sanitized

    digest = hashlib.sha256(sanitized.encode("utf-8")).hexdigest()[:8]
    prefix_length = _RESPONSE_FORMAT_NAME_MAX_LENGTH - len(digest) - 1
    prefix = sanitized[:prefix_length].rstrip("_-") or "structured_response"
    return f"{prefix}_{digest}"[:_RESPONSE_FORMAT_NAME_MAX_LENGTH]


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
                "content_diagnostics": _truncation_content_diagnostics(first),
            },
        )
    message = first.get("message")
    if not isinstance(message, dict):
        raise ModelProtocolError("Vision model response choice is missing message.")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content, str(finish_reason) if finish_reason else None
    raise ModelProtocolError("Vision model response message content is empty.")


def _truncation_content_diagnostics(choice: dict[str, Any]) -> dict[str, int]:
    """Content-free shape diagnostics for truncated generations.

    Distinguishes row rambling (many object opens), giant values (few opens,
    many chars), and degenerate whitespace loops without persisting document
    content into job errors.
    """
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    text = content if isinstance(content, str) else ""
    return {
        "content_chars": len(text),
        "whitespace_chars": sum(1 for char in text if char.isspace()),
        "trailing_whitespace_chars": len(text) - len(text.rstrip()),
        "object_open_count": text.count("{"),
        "array_open_count": text.count("["),
    }


def _usage_json(response: dict[str, Any]) -> dict[str, object]:
    usage = response.get("usage")
    return dict(usage) if isinstance(usage, dict) else {}


def _structured_content(
    raw_text: str,
    *,
    response_schema: dict[str, Any],
    response_schema_name: str | None,
) -> tuple[dict[str, object], dict[str, object]]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ModelProtocolError("Vision model content is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ModelProtocolError("Vision model JSON content must be an object.")
    _validate_structured_content(
        parsed,
        response_schema=response_schema,
        response_schema_name=response_schema_name,
    )
    confidence = parsed.get("confidence")
    if not isinstance(confidence, dict):
        confidence = {}
    return dict(parsed), confidence


def _validate_structured_content(
    parsed: dict[str, Any],
    *,
    response_schema: dict[str, Any],
    response_schema_name: str | None,
) -> None:
    try:
        Draft202012Validator.check_schema(response_schema)
        Draft202012Validator(response_schema).validate(parsed)
    except SchemaError:
        raise ModelProtocolError(
            "Vision response schema is not a valid JSON Schema.",
            details={"schema_name": response_schema_name},
        ) from None
    except ValidationError as exc:
        validator = exc.validator
        path = list(exc.path)
        raise ModelProtocolError(
            "Vision model JSON content does not match response schema.",
            details={
                "schema_name": response_schema_name,
                "validator": validator,
                "path": path,
            },
        ) from None
