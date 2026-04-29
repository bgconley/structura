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
    assert "Return compact candidate JSON" in client.request.prompt
    assert result.raw_output_json["semanticTask"]["semanticRegionId"] == str(task.region_id)


def test_granite_gateway_routes_invoice_tables_to_model_output_schema() -> None:
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

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert "<tables_json>" in client.request.prompt
    assert client.request.response_schema_name == "granite_invoice_line_items.v1"
    assert client.request.response_json_schema is not None
    assert "line_items" in client.request.response_json_schema["properties"]


def test_granite_gateway_forces_line_item_schema_when_qwen_task_label_is_kvp() -> None:
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
        granite_task="kvp",
        target_schema="invoice",
        expected_fields=("service_type", "service_cost", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen found service lines but mislabeled the Granite task.",
        confidence=0.81,
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert "<tables_json>" in client.request.prompt
    assert client.request.response_schema_name == "granite_invoice_line_items.v1"
    assert client.request.response_json_schema is not None


def test_granite_gateway_routes_payment_summary_to_kvp_schema_prompt() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="payment_summary",
        granite_task="kvp",
        target_schema="invoice",
        expected_fields=("amount_paid", "payment_reference"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen identified a payment summary.",
        confidence=0.88,
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert "Return a JSON object matching this schema" in client.request.prompt
    assert "Return null for fields you cannot find" in client.request.prompt
    assert client.request.response_schema_name == "granite_payment_summary.v1"
    assert client.request.response_json_schema is not None
    assert "payments" in client.request.response_json_schema["properties"]


def test_granite_gateway_uses_larger_output_budget_for_live_structured_json() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
    )

    assert client.request is not None
    assert client.request.max_output_tokens == 4096


def test_granite_gateway_sends_only_semantic_grounded_page() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_two_page_images()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items",),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[1].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert len(client.request.image_inputs) == 1
    assert client.request.image_inputs[0].content == b"page-two"


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


def _source_with_two_page_images() -> ExtractionSourceDocument:
    first_page_id = uuid4()
    second_page_id = uuid4()
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
                page_id=first_page_id,
                page_number=1,
                text="Invoice cover",
                image_bytes=b"page-one",
                image_mime_type="image/png",
                image_sha256=hashlib.sha256(b"page-one").hexdigest(),
            ),
            ParsedPageText(
                page_id=second_page_id,
                page_number=2,
                text="Invoice total $42",
                image_bytes=b"page-two",
                image_mime_type="image/png",
                image_sha256=hashlib.sha256(b"page-two").hexdigest(),
            ),
        ],
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=2,
                ordinal=1,
                text="Invoice total $42",
            )
        ],
        tables=[],
    )
