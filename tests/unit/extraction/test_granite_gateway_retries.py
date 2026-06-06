from __future__ import annotations

import hashlib
from uuid import uuid4

from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef


def test_granite_gateway_retries_length_truncated_output_with_escalated_budget() -> None:
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="retail_order_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        expected_fields=("description", "quantity", "amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        metadata={"resolved_document_type": "retail_order"},
    )
    client = _TruncatingRetailClient()

    result = GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert len(client.requests) == 2
    assert client.requests[0].max_output_tokens == 4096
    assert client.requests[1].max_output_tokens == 8192
    assert client.requests[1].timeout_seconds == 150
    assert result.raw_output_json["requestBudget"]["maxOutputTokens"] == 8192
    assert result.raw_output_json["modelRequestAttempts"] == [
        {
            "attempt": 1,
            "status": "failed",
            "reason": "length_truncated",
            "maxOutputTokens": 4096,
        },
        {
            "attempt": 2,
            "status": "succeeded",
            "reason": "length_truncated_retry",
            "maxOutputTokens": 8192,
        },
    ]


def test_granite_gateway_retries_schema_invalid_structured_output_once() -> None:
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("description", "amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )
    client = _SchemaInvalidThenValidClient()

    result = GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert len(client.requests) == 2
    assert client.requests[0].response_schema_name == "granite_invoice_line_items.v1"
    assert client.requests[1].response_schema_name == "granite_invoice_line_items.v1"
    assert client.requests[0].max_output_tokens == client.requests[1].max_output_tokens == 2048
    assert result.raw_output_json["modelRequestAttempts"] == [
        {
            "attempt": 1,
            "status": "failed",
            "reason": "structured_output_invalid",
            "maxOutputTokens": 2048,
        },
        {
            "attempt": 2,
            "status": "succeeded",
            "reason": "structured_output_retry",
            "maxOutputTokens": 2048,
        },
    ]


class _TruncatingRetailClient:
    def __init__(self) -> None:
        self.requests: list[VisionGenerateRequest] = []

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        self.requests.append(request)
        if len(self.requests) == 1:
            raise ModelProtocolError(
                "Vision model response was truncated before valid JSON completed.",
                details={"finish_reason": "length"},
            )
        return _vision_response(
            request,
            normalized_json={
                "line_items": [
                    {
                        "ordinal": 1,
                        "description": "Tripod",
                        "quantity": "1",
                        "amount": "10.00",
                    }
                ],
                "totals": {},
                "confidence": {},
            },
        )


class _SchemaInvalidThenValidClient:
    def __init__(self) -> None:
        self.requests: list[VisionGenerateRequest] = []

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        self.requests.append(request)
        if len(self.requests) == 1:
            raise ModelProtocolError(
                "Vision model JSON content does not match response schema.",
                details={"validator": "required", "path": []},
            )
        return _vision_response(
            request,
            normalized_json={
                "line_items": [{"description": "Alignment", "amount": "99.00"}],
                "confidence": {},
            },
        )


def _vision_response(
    request: VisionGenerateRequest,
    *,
    normalized_json: dict[str, object],
) -> VisionGenerateResponse:
    return VisionGenerateResponse(
        profile_name=GRANITE_VISION_PROFILE,
        model_name="fake-granite",
        model_version="test",
        source_engine="granite_vision_3b",
        prompt_version=request.prompt_version,
        raw_text="{}",
        normalized_json=normalized_json,
        confidence_json={},
        input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
        latency_ms=1,
    )


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
                text="Line item Alignment $99.00",
                image_bytes=b"page-image",
                image_mime_type="image/png",
                image_sha256=image_sha256,
                width_points=1200,
                height_points=1600,
            )
        ],
        elements=[],
        tables=[],
    )
