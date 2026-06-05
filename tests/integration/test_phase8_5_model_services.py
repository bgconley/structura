from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from lib.config import get_settings
from lib.model_runtime.clients.qwen_vl import QwenVLClient
from lib.model_runtime.clients.visual_embeddings import VisualEmbeddingClient
from lib.model_runtime.contracts import (
    EmbeddingInput,
    EmbeddingRequest,
    ModelImageInput,
    VisionGenerateRequest,
)
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import QWEN_VL_PROFILE, VISUAL_EMBED_PROFILE, get_model_profile
from lib.search import SearchService
from lib.search.embeddings.text_model import TextModelEmbeddingGateway
from lib.search.embeddings.visual_model import VisualQueryEmbeddingGateway


def test_phase8_5_live_search_uses_model_backed_query_gateways(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    get_settings.cache_clear()

    try:
        service = SearchService()
    finally:
        get_settings.cache_clear()

    assert isinstance(service.embedding_gateway, TextModelEmbeddingGateway)
    assert isinstance(service.visual_embedding_gateway, VisualQueryEmbeddingGateway)
    assert service.embedding_profile.name == "qwen3-embedding-4b-1536"
    assert service.visual_embedding_profile.name == "qwen3-vl-embedding-2b-2048"


def test_phase8_5_vision_clients_reject_oversized_images_before_transport() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    qwen_profile = replace(get_model_profile(QWEN_VL_PROFILE), max_image_bytes=4)
    qwen = QwenVLClient(
        profile=qwen_profile,
        http_client_base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(handler),
    )
    oversized = b"12345"

    with pytest.raises(ModelProtocolError, match="byte limit"):
        qwen.generate(
            VisionGenerateRequest(
                profile_name=QWEN_VL_PROFILE,
                prompt_version="phase8_5-qwen-handwriting-v1",
                prompt="extract handwriting",
                image_inputs=(
                    ModelImageInput(
                        content=oversized,
                        mime_type="image/png",
                        sha256="",
                    ),
                ),
                response_schema_name="invoice",
                max_output_tokens=512,
                temperature=0.0,
                timeout_seconds=30,
            )
        )

    visual_profile = replace(get_model_profile(VISUAL_EMBED_PROFILE), max_image_bytes=4)
    visual = VisualEmbeddingClient(
        profile=visual_profile,
        http_client_base_url="http://model-vl-embed:8103",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelProtocolError, match="byte limit"):
        visual.embed(
            EmbeddingRequest(
                profile_name=VISUAL_EMBED_PROFILE,
                inputs=(
                    EmbeddingInput(
                        text="oversized image",
                        image_bytes=oversized,
                        mime_type="image/png",
                    ),
                ),
                output_dimensions=2048,
                timeout_seconds=30,
            )
        )

    assert calls == 0
