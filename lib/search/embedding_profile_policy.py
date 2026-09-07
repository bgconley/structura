"""Keep the vector producer and database filter in the same embedding space."""

from __future__ import annotations

from lib.search.embedding_gateway import EmbeddingGatewayError, EmbeddingProfile


def resolved_embedding_profile(
    selected: EmbeddingProfile, requested: EmbeddingProfile | None
) -> EmbeddingProfile:
    if requested is not None and requested != selected:
        raise EmbeddingGatewayError(
            "Requested embedding profile conflicts with the selected gateway."
        )
    return selected
