"""Bounded embedding HTTP orchestration; formats and validation live separately."""

from __future__ import annotations

import time
from dataclasses import replace

import httpx

from lib.model_runtime.clients.embedding_payload import (
    embedding_payload,
    uses_individual_requests,
    validate_embedding_request,
)
from lib.model_runtime.clients.embedding_response import response_vectors
from lib.model_runtime.contracts import EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.model_runtime.http_client import (
    ModelConfigurationError,
    ModelHttpClient,
    ModelProtocolError,
    ModelTimeoutError,
)
from lib.model_runtime.profiles import ModelProfile


def embedding_api_flavor(profile: ModelProfile) -> str:
    if profile.embedding_protocol is None:
        raise ModelConfigurationError("Embedding profile must declare its protocol.")
    return profile.embedding_protocol.api_flavor


class EmbeddingHttpClient:
    def __init__(
        self,
        *,
        profile: ModelProfile,
        http_client_base_url: str,
        requires_image: bool,
        transport: httpx.BaseTransport | None = None,
        api_key: str | None = None,
    ) -> None:
        if type(profile.output_dimensions) is not int or profile.output_dimensions <= 0:
            raise ModelConfigurationError("Embedding profiles must declare positive dimensions.")
        self.profile = profile
        self.requires_image = requires_image
        self.api_flavor = embedding_api_flavor(profile)
        if requires_image and self.api_flavor != "openai":
            raise ModelConfigurationError("Visual embeddings require an image-capable protocol.")
        self._http = ModelHttpClient(
            base_url=http_client_base_url,
            timeout_seconds=60,
            transport=transport,
            api_key=api_key,
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        validate_embedding_request(request, self.profile, requires_image=self.requires_image)
        protocol = self.profile.embedding_protocol
        if protocol is None:
            raise ModelConfigurationError("Embedding profile must declare its protocol.")
        start = time.monotonic()
        input_hashes = embedding_input_hashes(request, self.profile)
        requests = (
            tuple(replace(request, inputs=(item,)) for item in request.inputs)
            if uses_individual_requests(request, self.profile)
            else (request,)
        )
        vectors: list[tuple[float, ...]] = []
        model_name: str | None = None
        model_version: str | None = None
        for part in requests:
            remaining = request.timeout_seconds - (time.monotonic() - start)
            if remaining <= 0:
                raise ModelTimeoutError("Embedding request exceeded its total time budget.")
            raw = self._http.post_json_value(
                protocol.endpoint,
                embedding_payload(part, self.profile),
                timeout_seconds=remaining,
            )
            if time.monotonic() - start > request.timeout_seconds:
                raise ModelTimeoutError("Embedding request exceeded its total time budget.")
            parsed, reported_name, reported_version = response_vectors(
                raw, profile=self.profile, count=len(part.inputs)
            )
            if model_name is not None and (reported_name, reported_version) != (
                model_name,
                model_version,
            ):
                raise ModelProtocolError(
                    "Embedding batch responses have inconsistent model identity."
                )
            model_name, model_version = reported_name, reported_version
            vectors.extend(parsed)
        if model_name is None or model_version is None:
            raise ModelProtocolError("Embedding response is missing its model identity.")
        return EmbeddingResponse(
            profile_name=self.profile.name,
            model_name=model_name,
            model_version=model_version,
            dimensions=request.output_dimensions,
            vectors=tuple(vectors),
            input_sha256=input_hashes,
            latency_ms=max(0, int((time.monotonic() - start) * 1000)),
            identity_source=protocol.identity_policy,
            artifact_revision=protocol.artifact_revision,
        )
