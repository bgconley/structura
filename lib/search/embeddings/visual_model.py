from __future__ import annotations

from typing import Protocol

from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.profiles import VISUAL_EMBED_PROFILE, get_model_profile
from lib.search.embedding_gateway import EmbeddedText, VisualEmbeddingInput
from lib.search.embeddings.validation import (
    search_embedding_profile,
    validated_response_vectors,
)


class VisualEmbeddingClientProtocol(Protocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


class VisualModelEmbeddingGateway:
    def __init__(
        self,
        *,
        client: VisualEmbeddingClientProtocol,
        profile_name: str = VISUAL_EMBED_PROFILE,
    ) -> None:
        self.client = client
        self.model_profile = get_model_profile(profile_name)
        self.profile = search_embedding_profile(self.model_profile)

    def embed_assets(self, assets: list[VisualEmbeddingInput]) -> list[EmbeddedText]:
        response = self.client.embed(
            EmbeddingRequest(
                profile_name=self.model_profile.name,
                inputs=tuple(
                    EmbeddingInput(
                        text=asset.descriptor_text,
                        image_bytes=asset.image_bytes,
                        mime_type=asset.mime_type,
                    )
                    for asset in assets
                ),
                output_dimensions=self.profile.dimensions,
                timeout_seconds=30,
            )
        )
        vectors = validated_response_vectors(
            response,
            expected_count=len(assets),
            expected_dimensions=self.profile.dimensions,
        )
        return [
            EmbeddedText(text=asset.descriptor_text, values=list(vector), profile=self.profile)
            for asset, vector in zip(assets, vectors, strict=True)
        ]
