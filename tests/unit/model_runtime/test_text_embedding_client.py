from __future__ import annotations

import json

import httpx
import pytest

from lib.model_runtime.clients._embedding import embedding_api_flavor
from lib.model_runtime.clients.text_embeddings import TextEmbeddingClient
from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import (
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
    get_model_profile,
)


def test_embedding_api_flavor_is_declared_by_profile_backend() -> None:
    assert embedding_api_flavor(get_model_profile(TEXT_EMBED_PROFILE)) == "tei"
    assert embedding_api_flavor(get_model_profile(VISUAL_EMBED_PROFILE)) == "openai"


def test_text_embedding_client_speaks_tei_inputs_contract_and_validates_dimensions() -> None:
    vector = [0.0] * 1536
    vector[0] = 1.0
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/embed"
        seen_payloads.append(json.loads(request.read().decode()))
        return httpx.Response(200, json=[vector])

    client = TextEmbeddingClient(
        profile=get_model_profile(TEXT_EMBED_PROFILE),
        http_client_base_url="http://model-embed:8102",
        transport=httpx.MockTransport(handler),
    )

    response = client.embed(
        EmbeddingRequest(
            profile_name=TEXT_EMBED_PROFILE,
            inputs=(EmbeddingInput(text="invoice total balance due"),),
            output_dimensions=1536,
            timeout_seconds=30,
        )
    )

    assert response.dimensions == 1536
    assert response.vectors == (tuple(vector),)
    assert response.profile_name == TEXT_EMBED_PROFILE
    assert response.model_name == "Qwen/Qwen3-Embedding-4B"
    assert seen_payloads == [
        {
            "inputs": ["invoice total balance due"],
            "dimensions": 1536,
        }
    ]


def test_text_embedding_client_fails_loud_on_tei_422_instead_of_guessing_routes() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(422, json={"error": "deserialize error"})

    client = TextEmbeddingClient(
        profile=get_model_profile(TEXT_EMBED_PROFILE),
        http_client_base_url="http://model-embed:8102",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ModelProtocolError, match="HTTP 422"):
        client.embed(
            EmbeddingRequest(
                profile_name=TEXT_EMBED_PROFILE,
                inputs=(EmbeddingInput(text="invoice total balance due"),),
                output_dimensions=1536,
                timeout_seconds=30,
            )
        )

    assert seen_paths == ["/embed"]


def test_text_embedding_client_falls_back_to_openai_embedding_endpoint() -> None:
    vector = [0.0] * 1536
    vector[4] = 1.0
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path == "/embed":
            return httpx.Response(404, json={"error": "not_found"})
        payload = request.read().decode()
        assert "/v1/embeddings" == request.url.path
        assert "Qwen/Qwen3-Embedding-4B" in payload
        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3-Embedding-4B",
                "data": [{"embedding": vector}],
            },
        )

    client = TextEmbeddingClient(
        profile=get_model_profile(TEXT_EMBED_PROFILE),
        http_client_base_url="http://model-embed:8102",
        transport=httpx.MockTransport(handler),
    )

    response = client.embed(
        EmbeddingRequest(
            profile_name=TEXT_EMBED_PROFILE,
            inputs=(EmbeddingInput(text="invoice total balance due"),),
            output_dimensions=1536,
            timeout_seconds=30,
        )
    )

    assert seen_paths == ["/embed", "/v1/embeddings"]
    assert response.vectors == (tuple(vector),)


def test_text_embedding_client_rejects_wrong_dimensions() -> None:
    client = TextEmbeddingClient(
        profile=get_model_profile(TEXT_EMBED_PROFILE),
        http_client_base_url="http://model-embed:8102",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[[1.0, 2.0]])),
    )

    with pytest.raises(ModelProtocolError, match="dimension"):
        client.embed(
            EmbeddingRequest(
                profile_name=TEXT_EMBED_PROFILE,
                inputs=(EmbeddingInput(text="invoice"),),
                output_dimensions=1536,
                timeout_seconds=30,
            )
        )


def test_text_embedding_client_accepts_internal_adapter_dict_response_on_embed() -> None:
    vector = [0.0] * 1536
    vector[9] = 1.0
    client = TextEmbeddingClient(
        profile=get_model_profile(TEXT_EMBED_PROFILE),
        http_client_base_url="http://model-embed:8102",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "Qwen/Qwen3-Embedding-4B",
                    "model_version": "tei",
                    "data": [{"embedding": vector}],
                },
            )
        ),
    )

    response = client.embed(
        EmbeddingRequest(
            profile_name=TEXT_EMBED_PROFILE,
            inputs=(EmbeddingInput(text="invoice total balance due"),),
            output_dimensions=1536,
            timeout_seconds=30,
        )
    )

    assert response.vectors == (tuple(vector),)
    assert response.model_version == "tei"


def test_text_embedding_client_rejects_empty_text_input() -> None:
    client = TextEmbeddingClient(
        profile=get_model_profile(TEXT_EMBED_PROFILE),
        http_client_base_url="http://model-embed:8102",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[])),
    )

    with pytest.raises(ModelProtocolError, match="must not be empty"):
        client.embed(
            EmbeddingRequest(
                profile_name=TEXT_EMBED_PROFILE,
                inputs=(EmbeddingInput(text="   "),),
                output_dimensions=1536,
                timeout_seconds=30,
            )
        )
