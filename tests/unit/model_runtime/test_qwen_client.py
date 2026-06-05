from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import httpx
import pytest

from lib.model_runtime.clients.qwen_vl import QwenVLClient
from lib.model_runtime.contracts import ModelImageInput, VisionGenerateRequest
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import QWEN_VL_PROFILE, get_model_profile
from lib.semantic_annotations.schema import semantic_annotation_manifest_schema


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
        http_client_base_url="http://model-qwen-semantic:8104",
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
    assert payload["seed"] == 0
    assert payload["metadata"]["profile_name"] == QWEN_VL_PROFILE


def test_qwen_client_rejects_malformed_model_content() -> None:
    client = QwenVLClient(
        profile=get_model_profile(QWEN_VL_PROFILE),
        http_client_base_url="http://model-qwen-semantic:8104",
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


def test_qwen_client_rejects_images_above_profile_byte_limit_before_base64() -> None:
    profile = replace(get_model_profile(QWEN_VL_PROFILE), max_image_bytes=4)
    client = QwenVLClient(
        profile=profile,
        http_client_base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    oversized = b"12345"
    with pytest.raises(ModelProtocolError, match="byte limit"):
        client.generate(
            VisionGenerateRequest(
                profile_name=QWEN_VL_PROFILE,
                prompt_version="phase8_5-qwen-handwriting-v1",
                prompt="extract handwriting",
                image_inputs=(
                    ModelImageInput(
                        content=oversized,
                        mime_type="image/png",
                        sha256=hashlib.sha256(oversized).hexdigest(),
                    ),
                ),
                response_schema_name="invoice",
                max_output_tokens=512,
                temperature=0.0,
                timeout_seconds=30,
            )
        )


def test_qwen_client_sends_json_schema_structured_output_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3-VL-8B-Instruct",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "schema_name": "semantic_annotation_manifest",
                                    "schema_version": "v1",
                                    "document_type": "medical_eob",
                                    "pages": [],
                                    "regions": [],
                                    "quality_flags": {},
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
        http_client_base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(handler),
    )

    response = client.generate(
        VisionGenerateRequest(
            profile_name=QWEN_VL_PROFILE,
            prompt_version="phase8_5-semantic-smart-v1",
            prompt="Return JSON only",
            image_inputs=_request().image_inputs,
            response_schema_name="semantic_annotation_manifest",
            response_json_schema=semantic_annotation_manifest_schema(),
            max_output_tokens=4096,
            temperature=0.0,
            timeout_seconds=30,
        )
    )

    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "semantic_annotation_manifest",
            "schema": semantic_annotation_manifest_schema(),
            "strict": True,
        },
    }
    assert "structured_outputs" not in payload
    assert response.finish_reason is None
    assert response.structured_output_used is True


def test_qwen_client_fails_closed_when_structured_output_request_is_rejected() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        return httpx.Response(400, json={"error": "structured output unsupported"})

    client = QwenVLClient(
        profile=get_model_profile(QWEN_VL_PROFILE),
        http_client_base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ModelProtocolError, match="HTTP 400"):
        client.generate(
            VisionGenerateRequest(
                profile_name=QWEN_VL_PROFILE,
                prompt_version="phase8_5-semantic-smart-v3",
                prompt="Return JSON only",
                image_inputs=_request().image_inputs,
                response_schema_name="semantic_annotation_manifest",
                response_json_schema=semantic_annotation_manifest_schema(),
                max_output_tokens=4096,
                temperature=0.0,
                timeout_seconds=30,
            )
        )

    assert len(seen) == 1
    assert seen[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "semantic_annotation_manifest",
            "schema": semantic_annotation_manifest_schema(),
            "strict": True,
        },
    }
    assert "structured_outputs" not in seen[0]


def test_qwen_client_can_use_legacy_structured_outputs_payload_when_requested() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3-VL-8B-Instruct",
                "choices": [{"message": {"content": json.dumps({"normalized": {"ok": True}})}}],
            },
        )

    client = QwenVLClient(
        profile=get_model_profile(QWEN_VL_PROFILE),
        http_client_base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(handler),
    )

    client.generate(
        VisionGenerateRequest(
            profile_name=QWEN_VL_PROFILE,
            prompt_version="phase8_5-semantic-smart-v3",
            prompt="Return JSON only",
            image_inputs=_request().image_inputs,
            response_schema_name="semantic_annotation_manifest",
            response_json_schema=semantic_annotation_manifest_schema(),
            max_output_tokens=4096,
            temperature=0.0,
            timeout_seconds=30,
            structured_output_mode="structured_outputs_json",
        )
    )

    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["structured_outputs"] == {"json": semantic_annotation_manifest_schema()}
    assert "response_format" not in payload


def test_qwen_client_rejects_truncated_structured_content() -> None:
    client = QwenVLClient(
        profile=get_model_profile(QWEN_VL_PROFILE),
        http_client_base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "Qwen/Qwen3-VL-8B-Instruct",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 512,
                        "total_tokens": 522,
                    },
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {
                                "content": json.dumps(
                                    {
                                        "normalized": {"fields": []},
                                        "confidence": {"overall": 0.4},
                                    }
                                )
                            },
                        }
                    ],
                },
            )
        ),
    )

    with pytest.raises(ModelProtocolError, match="truncated") as excinfo:
        client.generate(_request())
    assert excinfo.value.details["finish_reason"] == "length"
    assert excinfo.value.details["usage"] == {
        "prompt_tokens": 10,
        "completion_tokens": 512,
        "total_tokens": 522,
    }


def test_qwen_client_accepts_direct_normalized_object_for_live_model_tolerance() -> None:
    client = QwenVLClient(
        profile=get_model_profile(QWEN_VL_PROFILE),
        http_client_base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "Qwen/Qwen3-VL-8B-Instruct",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps({"fields": [{"name": "total", "value": 42}]})
                            }
                        }
                    ],
                },
            )
        ),
    )

    response = client.generate(_request())

    assert response.normalized_json == {"fields": [{"name": "total", "value": 42}]}
    assert response.confidence_json == {}


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
