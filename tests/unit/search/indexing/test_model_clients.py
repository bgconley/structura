from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from lib.config import Settings
from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.model_clients import candidate_embedding_clients


def test_factory_preserves_frozen_spaces_credentials_and_full_response():
    config = index_configuration(model_mode="live")
    calls = []

    def response(request):
        payload = json.loads(request.content)
        visual = "messages" in payload
        calls.append((payload, request.headers.get("authorization")))
        return httpx.Response(
            200,
            json={
                "model": payload["model"],
                "model_version": "reported-test-version",
                "data": [{"index": 0, "embedding": [0.1] * (2048 if visual else 1536)}],
            },
        )

    settings = Settings(
        _env_file=None,
        model_mode="live",
        text_embed_profile="irrelevant-default",
        visual_embed_profile="irrelevant-default",
        model_text_embed_url="http://text.example",
        model_visual_embed_url="http://visual.example",
        model_text_embed_api_key=SecretStr("text-secret"),
        model_visual_embed_api_key=SecretStr("visual-secret"),
    )
    clients = candidate_embedding_clients(
        config,
        settings,
        text_transport=httpx.MockTransport(response),
        visual_transport=httpx.MockTransport(response),
    )
    for modality in config.modalities:
        client = clients.for_modality(modality)
        value = (
            EmbeddingInput(text="source text")
            if modality == "text"
            else EmbeddingInput(text="", image_bytes=b"wire-test-only", mime_type="image/png")
        )
        result = client.embed(
            EmbeddingRequest(
                profile_name=config.space(modality).profile,
                inputs=(value,),
                output_dimensions=config.space(modality).dimensions,
                timeout_seconds=90,
            )
        )
        assert result.model_version == "reported-test-version"
        assert result.identity_source == "reported_model"
        assert result.artifact_revision == config.space(modality).protocol.artifact_revision
        assert result.profile_name == config.space(modality).profile
    assert calls[0][1] == "Bearer text-secret" and calls[1][1] == "Bearer visual-secret"
    assert calls[0][0]["dimensions"] == 1536
    assert "dimensions" not in calls[1][0]
    assert calls[1][0]["messages"][1]["content"][0]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


@pytest.mark.parametrize("mode,config_mode", [("fixture", "live"), ("live", "fixture")])
def test_factory_has_no_silent_live_fixture_fallback(mode, config_mode):
    with pytest.raises(IndexCandidateError, match="explicit live"):
        candidate_embedding_clients(
            index_configuration(model_mode=config_mode), Settings(_env_file=None, model_mode=mode)
        )
