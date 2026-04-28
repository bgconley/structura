from __future__ import annotations

import math

from lib.model_runtime.contracts import EmbeddingResponse
from lib.model_runtime.profiles import ModelProfile
from lib.search.embedding_gateway import EmbeddingGatewayError, EmbeddingProfile


def search_embedding_profile(model_profile: ModelProfile) -> EmbeddingProfile:
    if model_profile.output_dimensions is None:
        raise EmbeddingGatewayError("Model profile must declare embedding dimensions.")
    name, _, version = model_profile.name.partition(":")
    return EmbeddingProfile(
        name=name,
        version=version or "v1",
        modality="visual" if model_profile.engine == "visual_embedding" else "text",
        dimensions=model_profile.output_dimensions,
        metric="cosine",
    )


def validated_response_vectors(
    response: EmbeddingResponse,
    *,
    expected_count: int,
    expected_dimensions: int,
) -> tuple[tuple[float, ...], ...]:
    if len(response.vectors) != expected_count:
        raise EmbeddingGatewayError("Model embedding response count does not match input count.")
    for vector in response.vectors:
        if len(vector) != expected_dimensions:
            raise EmbeddingGatewayError("Model embedding vector dimension does not match profile.")
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingGatewayError("Model embedding vector contains non-finite values.")
    return response.vectors
