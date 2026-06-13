from __future__ import annotations

import base64
import math
import time
from typing import Any

import httpx

from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.http_client import ModelHttpClient, ModelProtocolError
from lib.model_runtime.profiles import ModelProfile

TEI_API_FLAVOR = "tei"
OPENAI_API_FLAVOR = "openai"
INTERNAL_API_FLAVOR = "internal"

_BACKEND_API_FLAVORS = {
    "tei-compatible": TEI_API_FLAVOR,
    "vllm-embed": OPENAI_API_FLAVOR,
    "vllm-openai": OPENAI_API_FLAVOR,
}


def embedding_api_flavor(profile: ModelProfile) -> str:
    """Resolve the embedding server API flavor from the profile registry.

    The profile backend declares the deployed server contract, so request
    routing never depends on 404-fallback guesswork: TEI services receive the
    native `{"inputs": [...]}` payload on /embed, OpenAI-compatible servers
    (vLLM) receive /v1/embeddings requests, and unknown backends keep the
    legacy internal /embed adapter shape with an OpenAI fallback.
    """
    return _BACKEND_API_FLAVORS.get(profile.backend, INTERNAL_API_FLAVOR)


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
        self.api_flavor = embedding_api_flavor(profile)
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
        if not request.inputs:
            raise ModelProtocolError("Embedding request requires at least one input.")
        start = time.monotonic()
        input_hashes = tuple(item.sha256 for item in request.inputs)
        if self.api_flavor == TEI_API_FLAVOR and not self.requires_image:
            return self._embed_tei(request, start_monotonic=start, input_hashes=input_hashes)
        if self.api_flavor == OPENAI_API_FLAVOR:
            return self._embed_openai(request, start_monotonic=start, input_hashes=input_hashes)
        return self._embed_internal(request, start_monotonic=start, input_hashes=input_hashes)

    def _embed_tei(
        self,
        request: EmbeddingRequest,
        *,
        start_monotonic: float,
        input_hashes: tuple[str, ...],
    ) -> EmbeddingResponse:
        payload = {
            "inputs": [self._text_input(item) for item in request.inputs],
            "dimensions": request.output_dimensions,
        }
        try:
            response = self._http.post_json_value(
                "/embed",
                payload,
                timeout_seconds=request.timeout_seconds,
            )
        except ModelProtocolError as exc:
            if not _is_missing_route_error(exc):
                raise
            response = self._http.post_json(
                "/v1/embeddings",
                self._openai_embedding_payload(request),
                timeout_seconds=request.timeout_seconds,
            )
        return self._response(
            response,
            request=request,
            start_monotonic=start_monotonic,
            input_hashes=input_hashes,
        )

    def _embed_openai(
        self,
        request: EmbeddingRequest,
        *,
        start_monotonic: float,
        input_hashes: tuple[str, ...],
    ) -> EmbeddingResponse:
        if self.requires_image and len(request.inputs) > 1:
            return self._embed_openai_visual_inputs_individually(
                request,
                start_monotonic=start_monotonic,
                input_hashes=input_hashes,
            )
        response = self._http.post_json(
            "/v1/embeddings",
            self._openai_embedding_payload(request),
            timeout_seconds=request.timeout_seconds,
        )
        return self._response(
            response,
            request=request,
            start_monotonic=start_monotonic,
            input_hashes=input_hashes,
        )

    def _embed_internal(
        self,
        request: EmbeddingRequest,
        *,
        start_monotonic: float,
        input_hashes: tuple[str, ...],
    ) -> EmbeddingResponse:
        try:
            response: dict[str, Any] | list[Any] = self._http.post_json(
                "/embed",
                self._internal_payload(request),
                timeout_seconds=request.timeout_seconds,
            )
        except ModelProtocolError as exc:
            if not _is_missing_route_error(exc):
                raise
            if self.requires_image and len(request.inputs) > 1:
                return self._embed_openai_visual_inputs_individually(
                    request,
                    start_monotonic=start_monotonic,
                    input_hashes=input_hashes,
                )
            response = self._http.post_json(
                "/v1/embeddings",
                self._openai_embedding_payload(request),
                timeout_seconds=request.timeout_seconds,
            )
        return self._response(
            response,
            request=request,
            start_monotonic=start_monotonic,
            input_hashes=input_hashes,
        )

    def _embed_openai_visual_inputs_individually(
        self,
        request: EmbeddingRequest,
        *,
        start_monotonic: float,
        input_hashes: tuple[str, ...],
    ) -> EmbeddingResponse:
        vectors: list[tuple[float, ...]] = []
        model_name: str | None = None
        model_version = ""
        for item in request.inputs:
            single_request = EmbeddingRequest(
                profile_name=request.profile_name,
                inputs=(item,),
                output_dimensions=request.output_dimensions,
                timeout_seconds=request.timeout_seconds,
            )
            response = self._http.post_json(
                "/v1/embeddings",
                self._openai_embedding_payload(single_request),
                timeout_seconds=request.timeout_seconds,
            )
            vectors.extend(
                _vectors(
                    response,
                    dimensions=request.output_dimensions,
                    count=1,
                )
            )
            model_name = model_name or str(response.get("model") or self.profile.base_model)
            model_version = model_version or str(response.get("model_version") or "")
        return EmbeddingResponse(
            profile_name=self.profile.name,
            model_name=model_name or self.profile.base_model,
            model_version=model_version,
            dimensions=request.output_dimensions,
            vectors=tuple(vectors),
            input_sha256=input_hashes,
            latency_ms=max(0, int((time.monotonic() - start_monotonic) * 1000)),
        )

    def _response(
        self,
        response: dict[str, Any] | list[Any],
        *,
        request: EmbeddingRequest,
        start_monotonic: float,
        input_hashes: tuple[str, ...],
    ) -> EmbeddingResponse:
        if isinstance(response, list):
            vectors = _tei_vectors(
                response,
                dimensions=request.output_dimensions,
                count=len(request.inputs),
            )
            model_name = self.profile.base_model
            model_version = ""
        else:
            vectors = _vectors(
                response,
                dimensions=request.output_dimensions,
                count=len(request.inputs),
            )
            model_name = str(response.get("model") or self.profile.base_model)
            model_version = str(response.get("model_version") or "")
        return EmbeddingResponse(
            profile_name=self.profile.name,
            model_name=model_name,
            model_version=model_version,
            dimensions=request.output_dimensions,
            vectors=vectors,
            input_sha256=input_hashes,
            latency_ms=max(0, int((time.monotonic() - start_monotonic) * 1000)),
        )

    def _internal_payload(self, request: EmbeddingRequest) -> dict[str, Any]:
        if self.requires_image:
            max_inputs = self.profile.max_images_per_request
            if max_inputs is not None and len(request.inputs) > max_inputs:
                raise ModelProtocolError(
                    "Visual embedding request has too many image inputs for profile."
                )
        return {
            "model": self.profile.base_model,
            "input": [self._input_payload(item) for item in request.inputs],
            "dimensions": request.output_dimensions,
            "metadata": {"profile_name": request.profile_name},
        }

    def _input_payload(self, item: EmbeddingInput) -> object:
        if self.requires_image:
            image_bytes = self._validated_image_bytes(item)
            return {
                "text": item.text,
                "image": {
                    "mime_type": item.mime_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                },
            }
        return self._text_input(item)

    def _text_input(self, item: EmbeddingInput) -> str:
        if not item.text.strip():
            raise ModelProtocolError("Text embedding input must not be empty.")
        return item.text

    def _validated_image_bytes(self, item: EmbeddingInput) -> bytes:
        if not item.image_bytes or not item.mime_type or not item.mime_type.startswith("image/"):
            raise ModelProtocolError("Visual embedding input requires image bytes.")
        if (
            self.profile.max_image_bytes is not None
            and len(item.image_bytes) > self.profile.max_image_bytes
        ):
            raise ModelProtocolError("Visual embedding image input exceeds profile byte limit.")
        return item.image_bytes

    def _openai_embedding_payload(self, request: EmbeddingRequest) -> dict[str, Any]:
        if not self.requires_image:
            payload: dict[str, Any] = {
                "model": self.profile.base_model,
                "input": [item.text for item in request.inputs],
                "metadata": {"profile_name": request.profile_name},
            }
            if self.profile.engine != "visual_embedding":
                payload["dimensions"] = request.output_dimensions
            return payload
        if len(request.inputs) != 1:
            raise ModelProtocolError(
                "OpenAI-compatible visual embedding supports one image at a time."
            )
        item = request.inputs[0]
        image_bytes = self._validated_image_bytes(item)
        data_url = base64.b64encode(image_bytes).decode("ascii")
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
            "metadata": {"profile_name": request.profile_name},
        }


def _is_missing_route_error(exc: ModelProtocolError) -> bool:
    message = str(exc)
    return "HTTP 404" in message or "HTTP 405" in message


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
        parsed.append(_validated_vector(item["embedding"], dimensions=dimensions))
    return tuple(parsed)


def _tei_vectors(
    response: list[Any],
    *,
    dimensions: int,
    count: int,
) -> tuple[tuple[float, ...], ...]:
    if len(response) != count:
        raise ModelProtocolError("Embedding response vector count does not match request count.")
    parsed: list[tuple[float, ...]] = []
    for item in response:
        if not isinstance(item, list):
            raise ModelProtocolError("Embedding response item is missing an embedding vector.")
        parsed.append(_validated_vector(item, dimensions=dimensions))
    return tuple(parsed)


def _validated_vector(values: list[Any], *, dimensions: int) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if len(vector) != dimensions:
        raise ModelProtocolError("Embedding response dimension does not match profile.")
    if not all(math.isfinite(value) for value in vector):
        raise ModelProtocolError("Embedding response contains non-finite values.")
    return vector
