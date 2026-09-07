from __future__ import annotations

from typing import Literal, Protocol

from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.profiles import TEXT_EMBED_PROFILE, get_model_profile
from lib.search.embedding_gateway import EmbeddedText
from lib.search.embedding_identity import EmbeddingInputIdentity
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
        purpose: Literal["document", "query"] = "document",
    ) -> None:
        self.client = client
        self.model_profile = get_model_profile(profile_name)
        self.profile = search_embedding_profile(self.model_profile)
        self.purpose: Literal["document", "query"] = purpose

    def embed_texts(self, texts: list[str]) -> list[EmbeddedText]:
        request = EmbeddingRequest(
            profile_name=self.model_profile.name,
            inputs=tuple(EmbeddingInput(text=text) for text in texts),
            output_dimensions=self.profile.dimensions,
            timeout_seconds=30,
            purpose=self.purpose,
        )
        response = self.client.embed(request)
        vectors = validated_response_vectors(
            response,
            request=request,
            profile=self.model_profile,
        )
        return [
            EmbeddedText(
                text=text,
                values=list(vector),
                profile=self.profile,
                input_identity=EmbeddingInputIdentity(digest, "model-input-v1", request.purpose),
            )
            for text, vector, digest in zip(texts, vectors, response.input_sha256, strict=True)
        ]
