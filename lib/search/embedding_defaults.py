from __future__ import annotations

from typing import Any, Protocol

from lib.model_runtime.clients.text_embeddings import TextEmbeddingClient
from lib.model_runtime.clients.visual_embeddings import (
    VisualEmbeddingClient,
    VisualQueryEmbeddingClient,
)
from lib.model_runtime.profiles import get_model_profile
from lib.search.embedding_gateway import (
    DeterministicEmbeddingGateway,
    DeterministicVisualEmbeddingGateway,
    EmbeddingProfile,
    VisualEmbeddingInput,
    default_text_embedding_profile,
    default_visual_embedding_profile,
)
from lib.search.embeddings.text_model import TextModelEmbeddingGateway
from lib.search.embeddings.visual_model import (
    VisualModelEmbeddingGateway,
    VisualQueryEmbeddingGateway,
)


class TextEmbeddingGatewayProtocol(Protocol):
    profile: EmbeddingProfile

    def embed_texts(self, texts: list[str]) -> list[Any]: ...


class VisualAssetEmbeddingGatewayProtocol(Protocol):
    profile: EmbeddingProfile

    def embed_assets(self, assets: list[VisualEmbeddingInput]) -> list[Any]: ...


def default_text_embedding_gateway(
    *,
    settings: Any,
    profile: EmbeddingProfile | None = None,
) -> TextEmbeddingGatewayProtocol:
    if settings.model_mode == "fixture":
        resolved_profile = profile or default_text_embedding_profile(
            settings.embedding_text_dimensions
        )
        return DeterministicEmbeddingGateway(resolved_profile)
    model_profile = get_model_profile(settings.text_embed_profile)
    return TextModelEmbeddingGateway(
        client=TextEmbeddingClient(
            profile=model_profile,
            http_client_base_url=settings.model_text_embed_url,
        ),
        profile_name=model_profile.name,
    )


def default_visual_asset_embedding_gateway(
    *,
    settings: Any,
    profile: EmbeddingProfile | None = None,
) -> VisualAssetEmbeddingGatewayProtocol:
    if settings.model_mode == "fixture":
        resolved_profile = profile or default_visual_embedding_profile(
            settings.embedding_visual_dimensions
        )
        return DeterministicVisualEmbeddingGateway(resolved_profile)
    model_profile = get_model_profile(settings.visual_embed_profile)
    return VisualModelEmbeddingGateway(
        client=VisualEmbeddingClient(
            profile=model_profile,
            http_client_base_url=settings.model_visual_embed_url,
        ),
        profile_name=model_profile.name,
    )


def default_visual_query_embedding_gateway(
    *,
    settings: Any,
    profile: EmbeddingProfile | None = None,
) -> TextEmbeddingGatewayProtocol:
    if settings.model_mode == "fixture":
        resolved_profile = profile or default_visual_embedding_profile(
            settings.embedding_visual_dimensions
        )
        return DeterministicVisualEmbeddingGateway(resolved_profile)
    model_profile = get_model_profile(settings.visual_embed_profile)
    return VisualQueryEmbeddingGateway(
        client=VisualQueryEmbeddingClient(
            profile=model_profile,
            http_client_base_url=settings.model_visual_embed_url,
        ),
        profile_name=model_profile.name,
    )
