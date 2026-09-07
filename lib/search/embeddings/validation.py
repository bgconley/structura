from __future__ import annotations

from lib.model_runtime.clients.embedding_response import validated_vector
from lib.model_runtime.contracts import EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.model_runtime.http_client import ModelProtocolError
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
    request: EmbeddingRequest,
    profile: ModelProfile,
) -> tuple[tuple[float, ...], ...]:
    protocol = profile.embedding_protocol
    if (
        protocol is None
        or response.profile_name != request.profile_name
        or response.profile_name != profile.name
        or response.dimensions != request.output_dimensions
        or response.dimensions != profile.output_dimensions
        or response.model_name != (profile.served_model_name or profile.base_model)
        or response.identity_source != protocol.identity_policy
        or response.artifact_revision != protocol.artifact_revision
    ):
        raise EmbeddingGatewayError("Model embedding response identity does not match its request.")
    if response.input_sha256 != embedding_input_hashes(request, profile):
        raise EmbeddingGatewayError(
            "Model embedding response input identity does not match request."
        )
    if len(response.vectors) != len(request.inputs):
        raise EmbeddingGatewayError("Model embedding response count does not match input count.")
    try:
        return tuple(
            validated_vector(vector, dimensions=request.output_dimensions)
            for vector in response.vectors
        )
    except ModelProtocolError as exc:
        raise EmbeddingGatewayError(str(exc)) from None
