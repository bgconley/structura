from __future__ import annotations

import hashlib
from dataclasses import dataclass

from lib.config import get_settings
from lib.model_runtime.contracts import EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.profiles import TEXT_EMBED_PROFILE, VISUAL_EMBED_PROFILE
from lib.search.embedding_gateway import VisualEmbeddingInput
from lib.search.embedding_service import EmbeddingService
from lib.search.embeddings.text_model import TextModelEmbeddingGateway
from lib.search.embeddings.visual_model import VisualModelEmbeddingGateway


@dataclass
class FakeEmbeddingClient:
    response: EmbeddingResponse
    request: EmbeddingRequest | None = None

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.request = request
        return self.response


def test_text_model_embedding_gateway_returns_live_profile_vectors() -> None:
    client = FakeEmbeddingClient(
        EmbeddingResponse(
            profile_name=TEXT_EMBED_PROFILE,
            model_name="Qwen/Qwen3-Embedding-4B",
            model_version="tei",
            dimensions=1536,
            vectors=(tuple([1.0, *([0.0] * 1535)]),),
            input_sha256=("hash",),
            latency_ms=3,
        )
    )

    embedded = TextModelEmbeddingGateway(client=client).embed_texts(["invoice total"])[0]

    assert embedded.profile.name == "qwen3-embedding-4b-1536"
    assert embedded.profile.version == "v1"
    assert embedded.profile.dimensions == 1536
    assert embedded.values[0] == 1.0
    assert client.request is not None
    assert client.request.profile_name == TEXT_EMBED_PROFILE


def test_visual_model_embedding_gateway_requires_image_bytes() -> None:
    image_bytes = b"visual-page"
    client = FakeEmbeddingClient(
        EmbeddingResponse(
            profile_name=VISUAL_EMBED_PROFILE,
            model_name="Qwen/Qwen3-VL-Embedding-2B",
            model_version="vllm",
            dimensions=2048,
            vectors=(tuple([0.0, 1.0, *([0.0] * 2046)]),),
            input_sha256=(hashlib.sha256(image_bytes).hexdigest(),),
            latency_ms=4,
        )
    )

    embedded = VisualModelEmbeddingGateway(client=client).embed_assets(
        [
            VisualEmbeddingInput(
                descriptor_text="handwritten page",
                image_bytes=image_bytes,
                mime_type="image/png",
                content_sha256=hashlib.sha256(image_bytes).hexdigest(),
            )
        ]
    )[0]

    assert embedded.profile.name == "qwen3-vl-embedding-2b-2048"
    assert embedded.profile.dimensions == 2048
    assert embedded.values[1] == 1.0
    assert client.request is not None
    assert client.request.inputs[0].image_bytes == image_bytes
    assert client.request.timeout_seconds == 90


def test_embedding_service_selects_live_model_gateways_when_model_mode_is_live(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    get_settings.cache_clear()

    try:
        service = EmbeddingService()
    finally:
        get_settings.cache_clear()

    assert isinstance(service.gateway, TextModelEmbeddingGateway)
    assert isinstance(service.visual_gateway, VisualModelEmbeddingGateway)
