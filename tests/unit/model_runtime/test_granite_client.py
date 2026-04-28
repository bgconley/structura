from __future__ import annotations

import hashlib
import json

import httpx

from lib.model_runtime.clients.granite_vision import GraniteVisionClient
from lib.model_runtime.contracts import ModelImageInput, VisionGenerateRequest
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE, get_model_profile


def test_granite_client_returns_structured_visual_extraction_provenance() -> None:
    image_sha256 = hashlib.sha256(b"page-image").hexdigest()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "ibm-granite/granite-4.0-3b-vision",
                "model_version": "bf16",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "normalized": {
                                        "tables": [{"columns": ["date", "amount"], "rows": 2}]
                                    },
                                    "confidence": {"table_structure": 0.82},
                                }
                            )
                        }
                    }
                ],
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
            max_output_tokens=1024,
            temperature=0.0,
            timeout_seconds=30,
        )
    )

    assert response.source_engine == "granite_vision_3b"
    assert response.profile_name == GRANITE_VISION_PROFILE
    assert response.normalized_json == {"tables": [{"columns": ["date", "amount"], "rows": 2}]}
    assert response.confidence_json == {"table_structure": 0.82}
