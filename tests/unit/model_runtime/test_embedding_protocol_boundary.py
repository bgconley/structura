from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, Literal

import httpx
import pytest

from lib.model_runtime.clients import _embedding
from lib.model_runtime.clients.text_embeddings import TextEmbeddingClient
from lib.model_runtime.clients.visual_embeddings import (
    VisualEmbeddingClient,
    VisualQueryEmbeddingClient,
)
from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.model_runtime.http_client import (
    ModelConfigurationError,
    ModelProtocolError,
    ModelTimeoutError,
)
from lib.model_runtime.profiles import (
    TEXT_EMBED_BLACKBIRD_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_BLACKBIRD_PROFILE,
    get_model_profile,
)


def embedding_request(
    *, purpose: Literal["document", "query"] = "document", texts=("first", "second")
) -> EmbeddingRequest:
    return EmbeddingRequest(
        profile_name=TEXT_EMBED_BLACKBIRD_PROFILE,
        inputs=tuple(EmbeddingInput(text=text) for text in texts),
        output_dimensions=1536,
        timeout_seconds=30,
        purpose=purpose,
    )


def vector(index=0, dimensions=1536) -> list[float]:
    result = [0.0] * dimensions
    result[index] = 1.0
    return result


def client_for(response: dict[str, Any]) -> TextEmbeddingClient:
    return TextEmbeddingClient(
        profile=get_model_profile(TEXT_EMBED_BLACKBIRD_PROFILE),
        http_client_base_url="http://embedding.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=response)),
    )


def test_openai_batch_uses_indexes_not_response_array_order() -> None:
    response = client_for(
        {
            "model": "Qwen/Qwen3-Embedding-4B",
            "data": [{"index": 1, "embedding": vector(1)}, {"index": 0, "embedding": vector(0)}],
        }
    ).embed(embedding_request())
    assert response.vectors == (tuple(vector(0)), tuple(vector(1)))
    assert response.identity_source == "reported_model"
    assert response.artifact_revision == "5cf2132abc99cad020ac570b19d031efec650f2b"


@pytest.mark.parametrize("indexes", [[0, 0], [0, 2], [-1, 1], [None, 1], [True, 1], [0.0, 1]])
def test_ambiguous_or_missing_indexes_never_reassociate_inputs(indexes) -> None:
    response = {
        "model": "Qwen/Qwen3-Embedding-4B",
        "data": [{"index": index, "embedding": vector()} for index in indexes],
    }
    with pytest.raises(ModelProtocolError, match="indexes"):
        client_for(response).embed(embedding_request())


@pytest.mark.parametrize("model", [None, "", 12, "another-model"])
def test_missing_or_wrong_reported_model_never_inherits_profile_identity(model) -> None:
    with pytest.raises(ModelProtocolError, match="model"):
        client_for({"model": model, "data": [{"index": 0, "embedding": vector()}]}).embed(
            embedding_request(texts=("document",))
        )


@pytest.mark.parametrize(
    "values",
    [
        [0.0] * 1536,
        [True, *([0.0] * 1535)],
        ["1", *([0.0] * 1535)],
        [None, *([0.0] * 1535)],
        [float("nan"), *([0.0] * 1535)],
        [float("inf"), *([0.0] * 1535)],
        [1e100, *([0.0] * 1535)],
        [1e-300, *([0.0] * 1535)],
    ],
)
def test_vectors_require_real_finite_indexable_nonzero_numbers(values) -> None:
    # Raw JSON intentionally exercises NaN/Infinity handling at the HTTP boundary.
    payload = json.dumps(
        {"model": "Qwen/Qwen3-Embedding-4B", "data": [{"index": 0, "embedding": values}]}
    )
    client = TextEmbeddingClient(
        profile=get_model_profile(TEXT_EMBED_BLACKBIRD_PROFILE),
        http_client_base_url="http://embedding.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=payload)),
    )
    with pytest.raises(ModelProtocolError):
        client.embed(embedding_request(texts=("document",)))


def test_query_instructions_authentication_and_document_text_are_exact() -> None:
    payloads = []
    profile = get_model_profile(TEXT_EMBED_BLACKBIRD_PROFILE)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        assert request.headers["authorization"] == "Bearer synthetic-private-token"
        payloads.append(json.loads(request.read()))
        return httpx.Response(
            200, json={"model": profile.base_model, "data": [{"index": 0, "embedding": vector()}]}
        )

    client = TextEmbeddingClient(
        profile=profile,
        http_client_base_url="http://embedding.test",
        api_key="synthetic-private-token",
        transport=httpx.MockTransport(handler),
    )
    client.embed(embedding_request(texts=("invoice",)))
    client.embed(embedding_request(purpose="query", texts=("invoice",)))
    assert payloads[0]["input"] == ["invoice"]
    assert payloads[1]["input"] == [
        "Instruct: Given a web search query, retrieve relevant passages that answer the query"
        "\nQuery:invoice"
    ]
    assert all(item["dimensions"] == 1536 for item in payloads)
    assert all(item["model"] == "Qwen/Qwen3-Embedding-4B" for item in payloads)


def test_v2_visual_images_and_text_queries_share_the_messages_format() -> None:
    payloads = []
    profile = get_model_profile(VISUAL_EMBED_BLACKBIRD_PROFILE)

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.read()))
        assert request.headers["authorization"] == "Bearer visual-token"
        return httpx.Response(
            200,
            json={
                "model": profile.base_model,
                "data": [{"index": 0, "embedding": vector(dimensions=2048)}],
            },
        )

    settings: dict[str, Any] = dict(
        profile=profile,
        http_client_base_url="http://embedding.test",
        api_key="visual-token",
        transport=httpx.MockTransport(handler),
    )
    VisualEmbeddingClient(**settings).embed(
        EmbeddingRequest(
            profile_name=profile.name,
            inputs=(EmbeddingInput(text="page", image_bytes=b"image", mime_type="image/png"),),
            output_dimensions=2048,
            timeout_seconds=30,
        )
    )
    VisualQueryEmbeddingClient(**settings).embed(
        EmbeddingRequest(
            profile_name=profile.name,
            inputs=(EmbeddingInput(text="receipt"), EmbeddingInput(text="invoice")),
            output_dimensions=2048,
            timeout_seconds=30,
            purpose="query",
        )
    )
    assert len(payloads) == 3
    assert all("input" not in item and "dimensions" not in item for item in payloads)
    assert all(
        item["messages"][0]
        == {"role": "system", "content": [{"type": "text", "text": "Represent the user's input."}]}
        for item in payloads
    )
    assert payloads[0]["messages"][1]["content"][0]["type"] == "image_url"
    assert payloads[1]["messages"][1]["content"] == [{"type": "text", "text": "receipt"}]
    assert payloads[2]["messages"][1]["content"] == [{"type": "text", "text": "invoice"}]


def test_complete_input_fingerprint_changes_for_every_input_and_space_component() -> None:
    profile = get_model_profile(VISUAL_EMBED_BLACKBIRD_PROFILE)
    assert profile.embedding_protocol is not None
    item = EmbeddingInput(text="page", image_bytes=b"image", mime_type="image/png")
    request = EmbeddingRequest(
        profile_name=profile.name, inputs=(item,), output_dimensions=2048, timeout_seconds=30
    )
    baseline = embedding_input_hashes(request, profile)
    changes = [
        replace(request, inputs=(replace(item, text="different context"),)),
        replace(request, inputs=(replace(item, image_bytes=b"other image"),)),
        replace(request, inputs=(replace(item, mime_type="image/jpeg"),)),
        replace(request, purpose="query"),
        replace(request, output_dimensions=1536),
    ]
    assert all(embedding_input_hashes(change, profile) != baseline for change in changes)
    assert embedding_input_hashes(request, replace(profile, name="other:v3")) != baseline
    assert (
        embedding_input_hashes(
            request,
            replace(
                profile,
                embedding_protocol=replace(
                    profile.embedding_protocol, artifact_revision="other-revision"
                ),
            ),
        )
        != baseline
    )


def test_undeclared_profile_and_empty_openai_text_fail_before_dispatch() -> None:
    profile = get_model_profile(TEXT_EMBED_BLACKBIRD_PROFILE)
    with pytest.raises(ModelConfigurationError, match="protocol"):
        TextEmbeddingClient(
            profile=replace(profile, embedding_protocol=None),
            http_client_base_url="http://embedding.test",
        )
    calls = []
    client = TextEmbeddingClient(
        profile=profile,
        http_client_base_url="http://embedding.test",
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, json={})
        ),
    )
    with pytest.raises(ModelProtocolError, match="empty"):
        client.embed(embedding_request(texts=("valid", " ")))
    assert not calls


def test_historical_tei_identity_is_explicitly_deployment_pinned() -> None:
    profile = get_model_profile(TEXT_EMBED_PROFILE)
    client = TextEmbeddingClient(
        profile=profile,
        http_client_base_url="http://embedding.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[vector()])),
    )
    result = client.embed(
        replace(embedding_request(texts=("document",)), profile_name=profile.name)
    )
    assert result.identity_source == "deployment_pinned"
    assert result.artifact_revision is None
    assert result.model_version == ""


def test_visual_batch_uses_one_total_timeout_budget(monkeypatch) -> None:
    now = 0.0
    timeouts = []
    profile = get_model_profile(VISUAL_EMBED_BLACKBIRD_PROFILE)
    monkeypatch.setattr(_embedding, "time", SimpleNamespace(monotonic=lambda: now))

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal now
        timeouts.append(request.extensions["timeout"]["read"])
        now += 40
        return httpx.Response(
            200,
            json={
                "model": profile.base_model,
                "data": [{"index": 0, "embedding": vector(dimensions=2048)}],
            },
        )

    client = VisualQueryEmbeddingClient(
        profile=profile,
        http_client_base_url="http://embedding.test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelTimeoutError, match="total time budget"):
        client.embed(
            EmbeddingRequest(
                profile_name=profile.name,
                inputs=(EmbeddingInput(text="first"), EmbeddingInput(text="second")),
                output_dimensions=2048,
                timeout_seconds=60,
                purpose="query",
            )
        )
    assert timeouts == [60, 20]


def test_visual_batch_rejects_model_revision_changes_between_responses() -> None:
    profile = get_model_profile(VISUAL_EMBED_BLACKBIRD_PROFILE)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "model": profile.base_model,
                "model_version": str(calls),
                "data": [{"index": 0, "embedding": vector(dimensions=2048)}],
            },
        )

    client = VisualQueryEmbeddingClient(
        profile=profile,
        http_client_base_url="http://embedding.test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ModelProtocolError, match="inconsistent model identity"):
        client.embed(
            EmbeddingRequest(
                profile_name=profile.name,
                inputs=(EmbeddingInput(text="first"), EmbeddingInput(text="second")),
                output_dimensions=2048,
                timeout_seconds=60,
                purpose="query",
            )
        )


def test_invalid_later_image_is_rejected_before_any_batch_dispatch() -> None:
    profile = get_model_profile(VISUAL_EMBED_BLACKBIRD_PROFILE)
    calls = []
    client = VisualEmbeddingClient(
        profile=profile,
        http_client_base_url="http://embedding.test",
        transport=httpx.MockTransport(
            lambda request: calls.append(request) or httpx.Response(200, json={})
        ),
    )
    with pytest.raises(ModelProtocolError, match="image"):
        client.embed(
            EmbeddingRequest(
                profile_name=profile.name,
                inputs=(
                    EmbeddingInput(text="first", image_bytes=b"image", mime_type="image/png"),
                    EmbeddingInput(text="second", image_bytes=b"", mime_type="image/png"),
                ),
                output_dimensions=2048,
                timeout_seconds=60,
            )
        )
    assert not calls
