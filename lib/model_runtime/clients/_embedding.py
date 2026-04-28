from __future__ import annotations

import base64
import math
import time
from typing import Any

import httpx

from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.http_client import ModelHttpClient, ModelProtocolError
from lib.model_runtime.profiles import ModelProfile


class EmbeddingHttpClient:
    def __init__(
        self,
        *,
        profile: ModelProfile,
        http_client_base_url: str,
        requires_image: bool,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if profile.output_dimensions is None:
            raise ValueError("Embedding profiles must declare output dimensions.")
        self.profile = profile
        self.requires_image = requires_image
        self._http = ModelHttpClient(
            base_url=http_client_base_url,
            timeout_seconds=60,
            transport=transport,
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        if request.profile_name != self.profile.name:
            raise ModelProtocolError("Embedding request profile does not match client profile.")
        if request.output_dimensions != self.profile.output_dimensions:
            raise ModelProtocolError("Embedding request dimension does not match client profile.")
        start = time.monotonic()
        payload, input_hashes = self._payload(request)
        try:
            response = self._http.post_json(
                "/embed",
                payload,
                timeout_seconds=request.timeout_seconds,
            )
        except ModelProtocolError as exc:
            if "HTTP 404" not in str(exc) and "HTTP 405" not in str(exc):
                raise
            response = self._http.post_json(
                "/v1/embeddings",
                self._openai_embedding_payload(request),
                timeout_seconds=request.timeout_seconds,
            )
        vectors = _vectors(
            response,
            dimensions=request.output_dimensions,
            count=len(request.inputs),
        )
        return EmbeddingResponse(
            profile_name=self.profile.name,
            model_name=str(response.get("model") or self.profile.base_model),
            model_version=str(response.get("model_version") or ""),
            dimensions=request.output_dimensions,
            vectors=vectors,
            input_sha256=input_hashes,
            latency_ms=max(0, int((time.monotonic() - start) * 1000)),
        )

    def _payload(self, request: EmbeddingRequest) -> tuple[dict[str, Any], tuple[str, ...]]:
        if not request.inputs:
            raise ModelProtocolError("Embedding request requires at least one input.")
        inputs = [self._input_payload(item) for item in request.inputs]
        return (
            {
                "model": self.profile.base_model,
                "input": inputs,
                "dimensions": request.output_dimensions,
                "metadata": {"profile_name": request.profile_name},
            },
            tuple(item.sha256 for item in request.inputs),
        )

    def _input_payload(self, item: EmbeddingInput) -> object:
        if self.requires_image:
            if (
                not item.image_bytes
                or not item.mime_type
                or not item.mime_type.startswith("image/")
            ):
                raise ModelProtocolError("Visual embedding input requires image bytes.")
            return {
                "text": item.text,
                "image": {
                    "mime_type": item.mime_type,
                    "data": base64.b64encode(item.image_bytes).decode("ascii"),
                },
            }
        if not item.text.strip():
            raise ModelProtocolError("Text embedding input must not be empty.")
        return item.text

    def _openai_embedding_payload(self, request: EmbeddingRequest) -> dict[str, Any]:
        if not self.requires_image:
            return {
                "model": self.profile.base_model,
                "input": [item.text for item in request.inputs],
                "dimensions": request.output_dimensions,
                "metadata": {"profile_name": request.profile_name},
            }
        if len(request.inputs) != 1:
            raise ModelProtocolError(
                "OpenAI-compatible visual embedding fallback supports one image at a time."
            )
        item = request.inputs[0]
        if not item.image_bytes or not item.mime_type or not item.mime_type.startswith("image/"):
            raise ModelProtocolError("Visual embedding input requires image bytes.")
        data_url = base64.b64encode(item.image_bytes).decode("ascii")
        content: list[dict[str, object]] = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{item.mime_type};base64,{data_url}"},
            }
        ]
        if item.text.strip():
            content.append({"type": "text", "text": item.text})
        return {
            "model": self.profile.base_model,
            "messages": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "Represent the user's input."}],
                },
                {"role": "user", "content": content},
            ],
            "dimensions": request.output_dimensions,
            "metadata": {"profile_name": request.profile_name},
        }


def _vectors(
    response: dict[str, Any],
    *,
    dimensions: int,
    count: int,
) -> tuple[tuple[float, ...], ...]:
    data = response.get("data")
    if not isinstance(data, list) or len(data) != count:
        raise ModelProtocolError("Embedding response vector count does not match request count.")
    parsed: list[tuple[float, ...]] = []
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
            raise ModelProtocolError("Embedding response item is missing an embedding vector.")
        vector = tuple(float(value) for value in item["embedding"])
        if len(vector) != dimensions:
            raise ModelProtocolError("Embedding response dimension does not match profile.")
        if not all(math.isfinite(value) for value in vector):
            raise ModelProtocolError("Embedding response contains non-finite values.")
        parsed.append(vector)
    return tuple(parsed)
