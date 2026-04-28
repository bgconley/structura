from __future__ import annotations

from typing import Protocol

from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.profiles import TEXT_EMBED_PROFILE, get_model_profile
from lib.search.embedding_gateway import EmbeddedText
from lib.search.embeddings.validation import (
    search_embedding_profile,
    validated_response_vectors,
)


class TextEmbeddingClientProtocol(Protocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


class TextModelEmbeddingGateway:
    def __init__(
        self,
        *,
        client: TextEmbeddingClientProtocol,
        profile_name: str = TEXT_EMBED_PROFILE,
    ) -> None:
        self.client = client
        self.model_profile = get_model_profile(profile_name)
        self.profile = search_embedding_profile(self.model_profile)

    def embed_texts(self, texts: list[str]) -> list[EmbeddedText]:
        response = self.client.embed(
            EmbeddingRequest(
                profile_name=self.model_profile.name,
                inputs=tuple(EmbeddingInput(text=text) for text in texts),
                output_dimensions=self.profile.dimensions,
                timeout_seconds=30,
            )
        )
        vectors = validated_response_vectors(
            response,
            expected_count=len(texts),
            expected_dimensions=self.profile.dimensions,
        )
        return [
            EmbeddedText(text=text, values=list(vector), profile=self.profile)
            for text, vector in zip(texts, vectors, strict=True)
        ]
