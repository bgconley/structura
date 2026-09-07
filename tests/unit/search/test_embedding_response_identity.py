from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import SecretStr

from lib.config.settings import Settings
from lib.model_runtime.clients.text_embeddings import TextEmbeddingClient
from lib.model_runtime.clients.visual_embeddings import (
    VisualEmbeddingClient,
    VisualQueryEmbeddingClient,
)
from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.model_runtime.http_client import ModelConfigurationError
from lib.model_runtime.profiles import (
    TEXT_EMBED_BLACKBIRD_PROFILE,
    VISUAL_EMBED_BLACKBIRD_PROFILE,
    get_model_profile,
)
from lib.search.embedding_defaults import (
    default_text_embedding_gateway,
    default_text_query_embedding_gateway,
    default_visual_asset_embedding_gateway,
    default_visual_query_embedding_gateway,
)
from lib.search.embedding_gateway import EmbeddingGatewayError
from lib.search.embeddings.text_model import TextModelEmbeddingGateway
from lib.search.embeddings.validation import validated_response_vectors
from lib.search.embeddings.visual_model import (
    VisualModelEmbeddingGateway,
    VisualQueryEmbeddingGateway,
)


def identity_fixture():
    profile = get_model_profile(TEXT_EMBED_BLACKBIRD_PROFILE)
    assert profile.embedding_protocol is not None
    request = EmbeddingRequest(
        profile_name=profile.name,
        inputs=(EmbeddingInput(text="first"), EmbeddingInput(text="second")),
        output_dimensions=1536,
        timeout_seconds=30,
        purpose="query",
    )
    vectors = (tuple([1.0, *([0.0] * 1535)]), tuple([0.0, 1.0, *([0.0] * 1534)]))
    response = EmbeddingResponse(
        profile_name=profile.name,
        model_name=profile.base_model,
        model_version="",
        dimensions=1536,
        vectors=vectors,
        input_sha256=embedding_input_hashes(request, profile),
        latency_ms=1,
        artifact_revision=profile.embedding_protocol.artifact_revision,
    )
    return profile, request, response


@pytest.mark.parametrize(
    "changes",
    [
        {"profile_name": "old-profile:v1"},
        {"model_name": "different-model"},
        {"dimensions": 2048},
        {"identity_source": "deployment_pinned"},
        {"artifact_revision": "different-revision"},
        {"input_sha256": ("different-input", "different-input")},
    ],
)
def test_gateway_rejects_a_well_shaped_vector_from_the_wrong_identity(changes) -> None:
    profile, request, response = identity_fixture()
    with pytest.raises(EmbeddingGatewayError, match="identity"):
        validated_response_vectors(replace(response, **changes), request=request, profile=profile)


def test_gateway_rejects_reordered_input_fingerprints_and_query_document_mix() -> None:
    profile, request, response = identity_fixture()
    with pytest.raises(EmbeddingGatewayError, match="input identity"):
        validated_response_vectors(
            replace(response, input_sha256=tuple(reversed(response.input_sha256))),
            request=request,
            profile=profile,
        )
    with pytest.raises(EmbeddingGatewayError, match="input identity"):
        validated_response_vectors(
            response, request=replace(request, purpose="document"), profile=profile
        )
    assert (
        validated_response_vectors(response, request=request, profile=profile) == response.vectors
    )


def test_live_query_factories_bind_the_correct_purpose_and_credentials(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    key_file = tmp_path / "visual-key"
    key_file.write_text("visual-secret\n")
    key_file.chmod(0o600)
    settings = Settings(
        model_mode="live",
        text_embed_profile=TEXT_EMBED_BLACKBIRD_PROFILE,
        visual_embed_profile=VISUAL_EMBED_BLACKBIRD_PROFILE,
        model_text_embed_api_key=SecretStr("text-secret"),
        model_visual_embed_api_key_file=key_file,
    )
    document = default_text_embedding_gateway(settings=settings)
    query = default_text_query_embedding_gateway(settings=settings)
    image = default_visual_asset_embedding_gateway(settings=settings)
    visual_query = default_visual_query_embedding_gateway(settings=settings)
    assert isinstance(document, TextModelEmbeddingGateway)
    assert isinstance(query, TextModelEmbeddingGateway)
    assert isinstance(image, VisualModelEmbeddingGateway)
    assert isinstance(visual_query, VisualQueryEmbeddingGateway)
    assert isinstance(document.client, TextEmbeddingClient)
    assert isinstance(query.client, TextEmbeddingClient)
    assert isinstance(image.client, VisualEmbeddingClient)
    assert isinstance(visual_query.client, VisualQueryEmbeddingClient)
    assert document.purpose == "document"
    assert query.purpose == "query"
    assert document.client._http._client.headers["authorization"] == "Bearer text-secret"
    assert query.client._http._client.headers["authorization"] == "Bearer text-secret"
    assert image.client._http._client.headers["authorization"] == "Bearer visual-secret"
    assert visual_query.client._http._client.headers["authorization"] == "Bearer visual-secret"
    assert "text-secret" not in repr(settings)


def test_embedding_factory_rejects_ambiguous_credential_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    key_file = tmp_path / "key"
    key_file.write_text("another-secret")
    key_file.chmod(0o600)
    settings = Settings(
        model_mode="live",
        model_text_embed_api_key=SecretStr("secret"),
        model_text_embed_api_key_file=key_file,
    )
    with pytest.raises(ModelConfigurationError, match="one model credential source"):
        default_text_embedding_gateway(settings=settings)
