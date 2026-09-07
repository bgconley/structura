from __future__ import annotations

import hashlib
from typing import Protocol

from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.profiles import VISUAL_EMBED_PROFILE, get_model_profile
from lib.search.embedding_gateway import EmbeddedText, EmbeddingGatewayError, VisualEmbeddingInput
from lib.search.embedding_identity import EmbeddingInputIdentity
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
        if any(
            hashlib.sha256(asset.image_bytes).hexdigest() != asset.content_sha256.lower()
            for asset in assets
        ):
            raise EmbeddingGatewayError("Visual embedding source hash does not match image bytes.")
        request = EmbeddingRequest(
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
            timeout_seconds=90,
        )
        response = self.client.embed(request)
        vectors = validated_response_vectors(
            response,
            request=request,
            profile=self.model_profile,
        )
        return [
            EmbeddedText(
                text=asset.descriptor_text,
                values=list(vector),
                profile=self.profile,
                input_identity=EmbeddingInputIdentity(digest, "model-input-v1", request.purpose),
            )
            for asset, vector, digest in zip(assets, vectors, response.input_sha256, strict=True)
        ]


class VisualQueryEmbeddingGateway:
    def __init__(
        self,
        *,
        client: VisualEmbeddingClientProtocol,
        profile_name: str = VISUAL_EMBED_PROFILE,
    ) -> None:
        self.client = client
        self.model_profile = get_model_profile(profile_name)
        self.profile = search_embedding_profile(self.model_profile)

    def embed_texts(self, texts: list[str]) -> list[EmbeddedText]:
        request = EmbeddingRequest(
            profile_name=self.model_profile.name,
            inputs=tuple(EmbeddingInput(text=text) for text in texts),
            output_dimensions=self.profile.dimensions,
            timeout_seconds=60,
            purpose="query",
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
