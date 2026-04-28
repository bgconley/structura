from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import QWEN_SEMANTIC_HQ_PROFILE, QWEN_SEMANTIC_PROFILE
from lib.semantic_annotations import qwen_gateway
from lib.semantic_annotations.fixture_gateway import FixtureSemanticAnnotationGateway
from lib.semantic_annotations.qwen_gateway import QwenSemanticAnnotationGateway


@dataclass
class FakeSemanticVisionClient:
    profile_name: str
    source_engine: str
    normalized_json: dict[str, object]
    request: VisionGenerateRequest | None = None

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        self.request = request
        return VisionGenerateResponse(
            profile_name=self.profile_name,
            model_name="fake-qwen",
            model_version="test",
            source_engine=self.source_engine,
            prompt_version=request.prompt_version,
            raw_text="{}",
            normalized_json=self.normalized_json,
            confidence_json={"overall": 0.88},
            input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
            latency_ms=1,
        )


def test_fixture_gateway_has_explicit_fixture_provenance() -> None:
    source = _source_with_page_image()

    result = FixtureSemanticAnnotationGateway().annotate(source, quality_mode="smart")

    assert result.manifest.source_engine == "system"
    assert result.manifest.model_name == "structura-fixture-semantic-annotator"
    assert result.manifest.profile_name == "structura-fixture-semantic-annotator:v1"
    assert result.manifest.regions[0].granite_task == "kvp"


def test_live_qwen_smart_gateway_builds_truthful_qwen2b_manifest() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=_semantic_payload(source.pages[0].page_id),
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert result.manifest.source_engine == "qwen3_vl_2b"
    assert result.manifest.profile_name == QWEN_SEMANTIC_PROFILE
    assert result.manifest.prompt_version == "phase8_5-semantic-smart-v1"
    assert client.request is not None
    assert "Docling context" in client.request.prompt
    assert client.request.image_inputs[0].content == b"page-image"


def test_live_qwen_high_quality_gateway_uses_qwen8b_profile() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=_semantic_payload(source.pages[0].page_id),
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert result.manifest.source_engine == "qwen3_vl_8b"
    assert result.manifest.profile_name == QWEN_SEMANTIC_HQ_PROFILE
    assert result.manifest.prompt_version == "phase8_5-semantic-high-quality-v1"


def test_live_qwen_gateway_rejects_malformed_model_output() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json={"pages": [], "regions": [{"semantic_type": "not_allowed"}]},
    )

    with pytest.raises(ModelProtocolError, match="semantic"):
        QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")


def test_qwen_semantic_client_uses_distinct_smart_and_high_quality_urls(
    monkeypatch,
) -> None:
    captured: list[tuple[str, str]] = []

    class RecordingClient:
        def __init__(self, *, profile: Any, http_client_base_url: str) -> None:
            captured.append((profile.name, http_client_base_url))

    monkeypatch.setattr(qwen_gateway, "QwenVLClient", RecordingClient)
    settings = qwen_gateway.Settings(
        model_qwen_semantic_url="http://model-qwen-semantic:8104",
        model_qwen_hq_url="http://model-qwen:8100",
    )

    qwen_gateway.QwenSemanticVisionClient.from_settings(settings)

    assert captured == [
        ("qwen3-vl-2b-semantic:v1", "http://model-qwen-semantic:8104"),
        ("qwen3-vl-8b-semantic-hq:v1", "http://model-qwen:8100"),
    ]


def _semantic_payload(page_id) -> dict[str, object]:
    return {
        "document_type": "invoice",
        "pages": [
            {
                "page_id": str(page_id),
                "page_number": 1,
                "page_role": "invoice_summary",
                "document_type_hint": "invoice",
                "extraction_usefulness": "high",
                "has_structured_targets": True,
                "confidence": 0.91,
            }
        ],
        "regions": [
            {
                "semantic_type": "billing_summary",
                "priority": "high",
                "granite_task": "kvp",
                "target_schema": "invoice",
                "expected_fields": ["invoice.total_amount"],
                "grounding": {"kind": "page", "page_id": str(page_id)},
                "reason": "Top of the page contains invoice totals.",
                "confidence": 0.89,
            }
        ],
    }


def _source_with_page_image() -> ExtractionSourceDocument:
    image_sha256 = hashlib.sha256(b"page-image").hexdigest()
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Invoice",
        original_filename="invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=uuid4(),
                page_number=1,
                text="Invoice total $42",
                image_bytes=b"page-image",
                image_mime_type="image/png",
                image_sha256=image_sha256,
            )
        ],
        elements=[],
        tables=[],
    )
