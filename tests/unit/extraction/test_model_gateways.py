from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import uuid4

from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.gateways.qwen_vl import QwenVLExtractionGateway
from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
)
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE, QWEN_VL_PROFILE
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef


@dataclass
class FakeVisionClient:
    source_engine: str
    profile_name: str
    request: VisionGenerateRequest | None = None

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        self.request = request
        return VisionGenerateResponse(
            profile_name=self.profile_name,
            model_name="fake-model",
            model_version="test",
            source_engine=self.source_engine,
            prompt_version=request.prompt_version,
            raw_text='{"normalized": {}, "confidence": {}}',
            normalized_json={"schema_name": request.response_schema_name, "from_model": True},
            confidence_json={"overall": 0.8},
            input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
            latency_ms=1,
        )


def test_qwen_extraction_gateway_truthfully_sets_qwen_provenance() -> None:
    client = FakeVisionClient(source_engine="qwen3_vl_8b", profile_name=QWEN_VL_PROFILE)
    source = _source_with_page_image()

    result = QwenVLExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="qwen_primary_review_required",
    )

    assert result.route.source_engine == "qwen3_vl_8b"
    assert result.route.model_name == "fake-model"
    assert result.raw_output_json["modelInvoked"] is True
    assert client.request is not None
    assert client.request.image_inputs[0].content == b"page-image"


def test_granite_extraction_gateway_truthfully_sets_granite_provenance() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()

    result = GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
    )

    assert result.route.source_engine == "granite_vision_3b"
    assert result.normalized_json["from_model"] is True
    assert result.raw_output_json["profileName"] == GRANITE_VISION_PROFILE


def test_granite_gateway_prompt_includes_grounded_semantic_task() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen identified an invoice table.",
        confidence=0.92,
    )

    result = GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert "Semantic task from Qwen annotation" in client.request.prompt
    assert "invoice_line_item_table" in client.request.prompt
    assert result.raw_output_json["semanticTask"]["semanticRegionId"] == str(task.region_id)


def _source_with_page_image() -> ExtractionSourceDocument:
    page_id = uuid4()
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
                page_id=page_id,
                page_number=1,
                text="Invoice total $42",
                image_bytes=b"page-image",
                image_mime_type="image/png",
                image_sha256=image_sha256,
            )
        ],
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=1,
                ordinal=1,
                text="Invoice total $42",
            )
        ],
        tables=[],
    )
