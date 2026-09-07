from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from lib.model_runtime.clients._openai_text import OpenAITextGenerateClient
from lib.model_runtime.clients.qwen_vl import QwenVLClient
from lib.model_runtime.contracts import ModelImageInput, TextGenerateRequest, VisionGenerateRequest
from lib.model_runtime.credentials import model_api_key
from lib.model_runtime.http_client import (
    ModelConfigurationError,
    ModelHttpClient,
    ModelProtocolError,
)
from lib.model_runtime.profiles import QWEN_INGESTION_PROFILE, get_model_profile
from lib.model_runtime.source_engines import is_model_source_engine, is_qwen_source_engine
from lib.semantic_annotations.qwen_gateway import _response_json_schema_for_profile

SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


@pytest.mark.parametrize("vision", [False, True])
def test_ingestion_sends_real_alias_auth_and_schema_with_truthful_provenance(vision):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "qwen38-27b-bf16-oxcart",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"text":"A-123"}',
                            "reasoning_content": "not final data",
                        },
                    }
                ],
            },
        )

    options = dict(
        profile=get_model_profile(QWEN_INGESTION_PROFILE),
        http_client_base_url="http://model:18012",
        api_key="synthetic-secret",
        transport=httpx.MockTransport(respond),
    )
    request = dict(
        profile_name=QWEN_INGESTION_PROFILE,
        prompt_version="synthetic-v1",
        prompt="transcribe",
        response_schema_name="synthetic.v1",
        max_output_tokens=128,
        temperature=0,
        timeout_seconds=10,
        response_json_schema=SCHEMA,
    )
    if vision:
        response = QwenVLClient(**options).generate(
            VisionGenerateRequest(
                **request, image_inputs=(ModelImageInput(b"pixels", "image/png", ""),)
            )
        )
    else:
        response = OpenAITextGenerateClient(**options).generate(TextGenerateRequest(**request))
    payload = json.loads(seen[0].content)
    assert seen[0].headers["Authorization"] == "Bearer synthetic-secret"
    assert payload["model"] == "qwen38-27b-bf16-oxcart"
    assert payload["response_format"]["json_schema"]["schema"] == SCHEMA
    assert "structured_outputs" not in payload
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert response.source_engine == "qwen3_8_27b"
    assert response.normalized_json == {"text": "A-123"}
    assert response.structured_output_used
    assert is_model_source_engine(response.source_engine)
    assert is_qwen_source_engine(response.source_engine)
    assert _response_json_schema_for_profile(QWEN_INGESTION_PROFILE) is not None


def test_credentials_are_private_bounded_and_not_discovered_through_symlinks(tmp_path):
    secret = tmp_path / "key"
    secret.write_text("synthetic-secret\n")
    secret.chmod(0o600)
    assert model_api_key(None, secret) == "synthetic-secret"
    link = tmp_path / "link"
    link.symlink_to(secret)
    with pytest.raises(ModelConfigurationError):
        model_api_key(None, link)
    secret.chmod(0o644)
    with pytest.raises(ModelConfigurationError):
        model_api_key(None, secret)
    with pytest.raises(ModelConfigurationError):
        model_api_key(SecretStr("synthetic-secret"), secret)


def test_authenticated_transport_never_follows_redirect_or_echoes_server_body():
    seen = []

    def redirect(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "http://elsewhere"}, text="private source")

    client = ModelHttpClient(
        base_url="http://model", api_key="synthetic-secret", transport=httpx.MockTransport(redirect)
    )
    with pytest.raises(ModelProtocolError) as error:
        client.post_json("/v1/chat/completions", {"messages": ["private source"]})
    assert len(seen) == 1
    assert "private source" not in repr(error.value.details)
    assert "synthetic-secret" not in repr(error.value.details)
    for url in ("http://user:secret@model", "http://model?token=secret", "http://model#secret"):
        with pytest.raises(ModelConfigurationError):
            ModelHttpClient(base_url=url)


def test_response_limit_stops_stream_before_unbounded_read():
    consumed = []

    class Body(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(10000):
                consumed.append(index)
                yield b"0123456789"

    client = ModelHttpClient(
        base_url="http://model",
        max_response_bytes=20,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Body())),
    )
    with pytest.raises(ModelProtocolError, match="too large"):
        client.post_json("/v1/chat/completions", {})
    assert len(consumed) < 10
