"""Validate embedding inputs and encode the profile's declared wire format."""

from __future__ import annotations

import base64
from typing import Any

from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest
from lib.model_runtime.embedding_protocol import VISUAL_SYSTEM_INSTRUCTION
from lib.model_runtime.http_client import ModelConfigurationError, ModelProtocolError
from lib.model_runtime.profiles import ModelProfile


def validate_embedding_request(
    request: EmbeddingRequest, profile: ModelProfile, *, requires_image: bool
) -> None:
    if request.profile_name != profile.name:
        raise ModelProtocolError("Embedding request profile does not match client profile.")
    if type(request.output_dimensions) is not int or (
        request.output_dimensions != profile.output_dimensions
    ):
        raise ModelProtocolError("Embedding request dimension does not match client profile.")
    if not request.inputs:
        raise ModelProtocolError("Embedding request requires at least one input.")
    if request.purpose not in {"document", "query"}:
        raise ModelProtocolError("Embedding request purpose is invalid.")
    if type(request.timeout_seconds) is not int or request.timeout_seconds <= 0:
        raise ModelProtocolError("Embedding request timeout must be positive.")
    for item in request.inputs:
        if not isinstance(item.text, str):
            raise ModelProtocolError("Embedding input text must be a string.")
        if requires_image:
            _validate_image(item, profile)
        elif item.image_bytes is not None or item.mime_type is not None:
            raise ModelProtocolError("Text embedding input cannot contain an image.")
        elif not item.text.strip():
            raise ModelProtocolError("Text embedding input must not be empty.")


def embedding_payload(request: EmbeddingRequest, profile: ModelProfile) -> dict[str, Any]:
    protocol = profile.embedding_protocol
    if protocol is None:
        raise ModelConfigurationError("Embedding profile must declare its protocol.")
    has_image = any(item.image_bytes is not None for item in request.inputs)
    if protocol.api_flavor == "tei":
        if has_image:
            raise ModelProtocolError("TEI text embedding cannot accept images.")
        payload: dict[str, Any] = {"inputs": [item.text for item in request.inputs]}
    else:
        payload = {
            "model": profile.served_model_name or profile.base_model,
            "metadata": {"profile_name": request.profile_name},
        }
        # Historical visual profiles retain raw text queries, but images have
        # always used messages. New visual profiles explicitly use messages for both.
        if protocol.input_format == "qwen_vl_messages" or has_image:
            if len(request.inputs) != 1:
                raise ModelProtocolError("Embedding messages require one input per request.")
            payload["messages"] = _messages(request.inputs[0])
        else:
            payload["input"] = [_text(item, request, profile) for item in request.inputs]
    if protocol.dimensions_policy == "requested":
        payload["dimensions"] = request.output_dimensions
    return payload


def uses_individual_requests(request: EmbeddingRequest, profile: ModelProfile) -> bool:
    protocol = profile.embedding_protocol
    return protocol is not None and (
        protocol.input_format == "qwen_vl_messages"
        or any(item.image_bytes is not None for item in request.inputs)
    )


def _text(item: EmbeddingInput, request: EmbeddingRequest, profile: ModelProfile) -> str:
    protocol = profile.embedding_protocol
    if protocol is not None and protocol.input_format == "qwen_text" and request.purpose == "query":
        return f"Instruct: {protocol.query_instruction}\nQuery:{item.text}"
    return item.text


def _messages(item: EmbeddingInput) -> list[dict[str, Any]]:
    content: list[dict[str, object]] = []
    if item.image_bytes is not None:
        encoded = base64.b64encode(item.image_bytes).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{item.mime_type};base64,{encoded}"},
            }
        )
    if item.text.strip():
        content.append({"type": "text", "text": item.text})
    return [
        {"role": "system", "content": [{"type": "text", "text": VISUAL_SYSTEM_INSTRUCTION}]},
        {"role": "user", "content": content},
    ]


def _validate_image(item: EmbeddingInput, profile: ModelProfile) -> None:
    if (
        not isinstance(item.image_bytes, bytes)
        or not item.image_bytes
        or item.mime_type not in {"image/png", "image/jpeg", "image/webp"}
    ):
        raise ModelProtocolError("Visual embedding input requires supported image bytes.")
    if profile.max_image_bytes is not None and len(item.image_bytes) > profile.max_image_bytes:
        raise ModelProtocolError("Visual embedding image input exceeds profile byte limit.")
    if profile.max_images_per_request is not None and profile.max_images_per_request < 1:
        raise ModelConfigurationError("Visual embedding profile must permit an image input.")
