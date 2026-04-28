from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from lib.model_runtime.clients.qwen_vl import QwenVLClient
from lib.model_runtime.contracts import ModelImageInput, VisionGenerateRequest
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import QWEN_VL_PROFILE, get_model_profile


def test_qwen_client_builds_multimodal_payload_and_returns_truthful_provenance() -> None:
    seen: dict[str, object] = {}
    image_sha256 = hashlib.sha256(b"image-bytes").hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3-VL-8B-Instruct",
                "model_version": "nvfp4-local",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "normalized": {"fields": [{"name": "total", "value": 42}]},
                                    "confidence": {"overall": 0.74},
                                }
                            )
                        }
                    }
                ],
            },
        )

    client = QwenVLClient(
        profile=get_model_profile(QWEN_VL_PROFILE),
        http_client_base_url="http://model-qwen:8100",
        transport=httpx.MockTransport(handler),
    )
    response = client.generate(
        VisionGenerateRequest(
            profile_name=QWEN_VL_PROFILE,
            prompt_version="phase8_5-qwen-handwriting-v1",
            prompt="extract handwriting",
            image_inputs=(
                ModelImageInput(
                    content=b"image-bytes",
                    mime_type="image/png",
                    sha256=image_sha256,
                ),
            ),
            response_schema_name="invoice",
            max_output_tokens=512,
            temperature=0.0,
            timeout_seconds=30,
        )
    )

    assert response.source_engine == "qwen3_vl_8b"
    assert response.profile_name == QWEN_VL_PROFILE
    assert response.model_name == "Qwen/Qwen3-VL-8B-Instruct"
    assert response.model_version == "nvfp4-local"
    assert response.normalized_json == {"fields": [{"name": "total", "value": 42}]}
    assert response.confidence_json == {"overall": 0.74}
    assert response.input_sha256 == (image_sha256,)

    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "Qwen/Qwen3-VL-8B-Instruct"
    content = payload["messages"][0]["content"]
    assert any(part["type"] == "image_url" for part in content)
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["metadata"]["profile_name"] == QWEN_VL_PROFILE


def test_qwen_client_rejects_malformed_model_content() -> None:
    client = QwenVLClient(
        profile=get_model_profile(QWEN_VL_PROFILE),
        http_client_base_url="http://model-qwen:8100",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "Qwen/Qwen3-VL-8B-Instruct",
                    "choices": [{"message": {"content": "not-json"}}],
                },
            )
        ),
    )

    with pytest.raises(ModelProtocolError, match="JSON"):
        client.generate(_request())


def _request() -> VisionGenerateRequest:
    image_sha256 = hashlib.sha256(b"image-bytes").hexdigest()
    return VisionGenerateRequest(
        profile_name=QWEN_VL_PROFILE,
        prompt_version="phase8_5-qwen-handwriting-v1",
        prompt="extract handwriting",
        image_inputs=(
            ModelImageInput(content=b"image-bytes", mime_type="image/png", sha256=image_sha256),
        ),
        response_schema_name="invoice",
        max_output_tokens=512,
        temperature=0.0,
        timeout_seconds=30,
    )
