from __future__ import annotations

import httpx
import pytest

from lib.model_runtime.clients.visual_embeddings import VisualEmbeddingClient
from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import VISUAL_EMBED_PROFILE, get_model_profile


def test_visual_embedding_client_requires_image_bytes_and_validates_1024_dimensions() -> None:
    vector = [0.0] * 1024
    vector[3] = 1.0
    client = VisualEmbeddingClient(
        profile=get_model_profile(VISUAL_EMBED_PROFILE),
        http_client_base_url="http://model-vl-embed:8103",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "Qwen/Qwen3-VL-Embedding-2B",
                    "model_version": "vllm-embed",
                    "data": [{"embedding": vector}],
                },
            )
        ),
    )

    response = client.embed(
        EmbeddingRequest(
            profile_name=VISUAL_EMBED_PROFILE,
            inputs=(
                EmbeddingInput(
                    text="handwritten degraded page",
                    image_bytes=b"image-bytes",
                    mime_type="image/png",
                ),
            ),
            output_dimensions=1024,
            timeout_seconds=30,
        )
    )

    assert response.dimensions == 1024
    assert response.profile_name == VISUAL_EMBED_PROFILE
    assert response.vectors == (tuple(vector),)
    assert response.input_sha256[0]


def test_visual_embedding_client_rejects_descriptor_only_input() -> None:
    client = VisualEmbeddingClient(
        profile=get_model_profile(VISUAL_EMBED_PROFILE),
        http_client_base_url="http://model-vl-embed:8103",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    with pytest.raises(ModelProtocolError, match="image"):
        client.embed(
            EmbeddingRequest(
                profile_name=VISUAL_EMBED_PROFILE,
                inputs=(EmbeddingInput(text="descriptor only"),),
                output_dimensions=1024,
                timeout_seconds=30,
            )
        )
