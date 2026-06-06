from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from lib.extraction.model_output_schemas import load_model_output_schema
from lib.model_runtime.clients.granite_vision import GraniteVisionClient
from lib.model_runtime.contracts import ModelImageInput, VisionGenerateRequest
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE, get_model_profile


def test_granite_client_requires_json_schema_before_transport() -> None:
    calls = 0
    image_sha256 = hashlib.sha256(b"page-image").hexdigest()

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    client = GraniteVisionClient(
        profile=get_model_profile(GRANITE_VISION_PROFILE),
        http_client_base_url="http://model-granite:8101",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ModelProtocolError, match="JSON Schema"):
        client.generate(
            VisionGenerateRequest(
                profile_name=GRANITE_VISION_PROFILE,
                prompt_version="phase8_5-granite-structured-v1",
                prompt="extract table structure",
                image_inputs=(
                    ModelImageInput(
                        content=b"page-image",
                        mime_type="image/png",
                        sha256=image_sha256,
                    ),
                ),
                response_schema_name="invoice",
                max_output_tokens=1024,
                temperature=0.0,
                timeout_seconds=30,
            )
        )

    assert calls == 0


def test_granite_client_returns_structured_visual_extraction_provenance() -> None:
    image_sha256 = hashlib.sha256(b"page-image").hexdigest()
    payload = {
        "tables": [{"columns": ["date", "amount"], "rows": 2}],
        "confidence": {"table_structure": 0.82},
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "ibm-granite/granite-4.0-3b-vision",
                "model_version": "bf16",
                "choices": [{"message": {"content": json.dumps(payload)}}],
            },
        )

    client = GraniteVisionClient(
        profile=get_model_profile(GRANITE_VISION_PROFILE),
        http_client_base_url="http://model-granite:8101",
        transport=httpx.MockTransport(handler),
    )

    response = client.generate(
        VisionGenerateRequest(
            profile_name=GRANITE_VISION_PROFILE,
            prompt_version="phase8_5-granite-structured-v1",
            prompt="extract table structure",
            image_inputs=(
                ModelImageInput(content=b"page-image", mime_type="image/png", sha256=image_sha256),
            ),
            response_schema_name="invoice",
            response_json_schema=_table_schema(),
            max_output_tokens=1024,
            temperature=0.0,
            timeout_seconds=30,
        )
    )

    assert response.source_engine == "granite_vision_3b"
    assert response.profile_name == GRANITE_VISION_PROFILE
    assert response.normalized_json == payload
    assert response.confidence_json == {"table_structure": 0.82}


def test_granite_client_preserves_schema_valid_confidence_in_direct_payload() -> None:
    image_sha256 = hashlib.sha256(b"page-image").hexdigest()
    payload = {
        "line_items": [],
        "totals": {
            "subtotal": None,
            "tax_total": None,
            "shipping_total": None,
            "discount_total": None,
            "total": None,
        },
        "confidence": {
            "overall": 0.81,
            "schema_fit": 0.79,
            "table_structure": 0.76,
        },
    }

    client = GraniteVisionClient(
        profile=get_model_profile(GRANITE_VISION_PROFILE),
        http_client_base_url="http://model-granite:8101",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "ibm-granite/granite-4.0-3b-vision",
                    "choices": [{"message": {"content": json.dumps(payload)}}],
                },
            )
        ),
    )

    response = client.generate(
        VisionGenerateRequest(
            profile_name=GRANITE_VISION_PROFILE,
            prompt_version="phase8_5-granite-structured-v1",
            prompt="extract table structure",
            image_inputs=(
                ModelImageInput(content=b"page-image", mime_type="image/png", sha256=image_sha256),
            ),
            response_schema_name="granite_invoice_line_items.v1",
            response_json_schema=load_model_output_schema("granite_invoice_line_items.v1").schema,
            max_output_tokens=1024,
            temperature=0.0,
            timeout_seconds=30,
        )
    )

    assert response.normalized_json == payload
    assert response.confidence_json == payload["confidence"]


def test_granite_client_preserves_schema_valid_normalized_wrapper_payload() -> None:
    image_sha256 = hashlib.sha256(b"page-image").hexdigest()
    payload = {
        "normalized": {"tables": [{"columns": ["date", "amount"], "rows": 2}]},
        "confidence": {"table_structure": 0.82},
    }

    client = GraniteVisionClient(
        profile=get_model_profile(GRANITE_VISION_PROFILE),
        http_client_base_url="http://model-granite:8101",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "ibm-granite/granite-4.0-3b-vision",
                    "choices": [{"message": {"content": json.dumps(payload)}}],
                },
            )
        ),
    )

    response = client.generate(
        VisionGenerateRequest(
            profile_name=GRANITE_VISION_PROFILE,
            prompt_version="phase8_5-granite-structured-v1",
            prompt="extract table structure",
            image_inputs=(
                ModelImageInput(content=b"page-image", mime_type="image/png", sha256=image_sha256),
            ),
            response_schema_name="legacy_wrapper_schema",
            response_json_schema=_legacy_wrapper_schema(),
            max_output_tokens=1024,
            temperature=0.0,
            timeout_seconds=30,
        )
    )

    assert response.normalized_json == payload
    assert response.confidence_json == payload["confidence"]


def test_granite_client_rejects_confidence_only_json_that_misses_required_payload() -> None:
    image_sha256 = hashlib.sha256(b"page-image").hexdigest()

    client = GraniteVisionClient(
        profile=get_model_profile(GRANITE_VISION_PROFILE),
        http_client_base_url="http://model-granite:8101",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "ibm-granite/granite-4.0-3b-vision",
                    "choices": [
                        {"message": {"content": json.dumps({"confidence": {"overall": 0.0}})}}
                    ],
                },
            )
        ),
    )

    with pytest.raises(ModelProtocolError, match="response schema"):
        client.generate(
            VisionGenerateRequest(
                profile_name=GRANITE_VISION_PROFILE,
                prompt_version="phase8_5-granite-structured-v1",
                prompt="extract table structure",
                image_inputs=(
                    ModelImageInput(
                        content=b"page-image",
                        mime_type="image/png",
                        sha256=image_sha256,
                    ),
                ),
                response_schema_name="invoice",
                response_json_schema=_table_schema(),
                max_output_tokens=1024,
                temperature=0.0,
                timeout_seconds=30,
            )
        )


def _table_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": ["tables", "confidence"],
        "additionalProperties": False,
        "properties": {
            "tables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["columns", "rows"],
                    "additionalProperties": False,
                    "properties": {
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "rows": {"type": "integer"},
                    },
                },
            },
            "confidence": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"table_structure": {"type": "number"}},
                "required": ["table_structure"],
            },
        },
    }


def _legacy_wrapper_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": ["normalized", "confidence"],
        "additionalProperties": False,
        "properties": {
            "normalized": {
                "type": "object",
                "required": ["tables"],
                "additionalProperties": False,
                "properties": {
                    "tables": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["columns", "rows"],
                            "additionalProperties": False,
                            "properties": {
                                "columns": {"type": "array", "items": {"type": "string"}},
                                "rows": {"type": "integer"},
                            },
                        },
                    }
                },
            },
            "confidence": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"table_structure": {"type": "number"}},
                "required": ["table_structure"],
            },
        },
    }
