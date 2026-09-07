"""Explicit controlled v2 transport fixture, never live or a source quality result."""

import json

from lib.model_runtime.contracts import VisionGenerateResponse
from tests.fixtures.page_understanding_sources import invoice_page, prose_page


class UnderstandingClient:
    def __init__(self, *, after_generate=lambda: None, fail_page=None):
        self.calls = []
        self.requests = []
        self.after_generate = after_generate
        self.fail_page = fail_page

    def generate(self, request):
        current = json.loads(
            request.prompt.split("Current page identity and untrusted native hint:\n")[1]
        )
        number = current["page_number"]
        self.calls.append(number)
        self.requests.append(request)
        if number == self.fail_page:
            raise RuntimeError("Controlled fixture outage")
        payload = invoice_page() if number == 1 else prose_page()
        payload["page_number"] = number
        self.after_generate()
        return VisionGenerateResponse(
            profile_name=request.profile_name,
            model_name="qwen38-27b-bf16-oxcart",
            model_version="explicit-understanding-test-fixture",
            source_engine="qwen3_8_27b",
            prompt_version=request.prompt_version,
            raw_text=json.dumps(payload, ensure_ascii=False),
            normalized_json=payload,
            confidence_json={},
            input_sha256=tuple(image.sha256 for image in request.image_inputs),
            latency_ms=1,
            finish_reason="stop",
            structured_output_used=True,
        )
