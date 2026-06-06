from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import uuid4

import pytest

from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE
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


def _invoice_line_item_task(source: ExtractionSourceDocument) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen identified a grounded invoice table.",
        confidence=0.92,
    )


def test_granite_extraction_gateway_rejects_missing_semantic_task() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )

    with pytest.raises(ModelProtocolError, match="semantic region task"):
        GraniteVisionExtractionGateway(client=client).extract(
            _source_with_page_image(),
            schema_name="invoice",
            route_profile="docling_plus_granite_structured",
        )

    assert client.request is None


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
        semantic_task=_invoice_line_item_task(source),
    )

    assert result.route.source_engine == "granite_vision_3b"
    assert result.raw_output_json["sourceEngine"] == "granite_vision_3b"
    assert result.raw_output_json["modelOutputPayload"]["from_model"] is True
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
    assert client.request.prompt.startswith("<tables_json>")
    assert "Extract line items as compact row candidates" in client.request.prompt
    assert "Return at most 20 row objects" in client.request.prompt
    assert "Do not output table dimensions, table cells, or table schema." in client.request.prompt
    assert "Do not include page summaries, row grids, coordinate dumps, or explanatory text." in (
        client.request.prompt
    )
    assert "JSON Schema:" not in client.request.prompt
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
    assert client.request.prompt.startswith("<tables_json>")
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
    assert "response schema supplied by the API" in client.request.prompt
    assert "JSON Schema:" not in client.request.prompt
    assert '"properties"' not in client.request.prompt
    assert "Return null or an empty list when evidence is not visible" in client.request.prompt
    assert '"payments":[]' in client.request.prompt
    assert client.request.response_schema_name == "granite_payment_summary.v1"
    assert client.request.response_json_schema is not None
    assert "payments" in client.request.response_json_schema["properties"]
    assert client.request.max_output_tokens == 1536


def test_granite_gateway_routes_coverage_decision_to_healthcare_contract() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="denial_or_coverage_decision",
        granite_task="kvp",
        target_schema="medical_eob",
        expected_fields=("denial_reason", "appeal_deadline"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen identified a coverage decision block.",
        confidence=0.91,
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="medical_eob",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.response_schema_name == "granite_healthcare_coverage_decision.v1"
    assert "denial_reason" in client.request.prompt
    assert client.request.response_json_schema is not None


def test_granite_gateway_routes_retail_order_tables_to_retail_contract() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
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
    )

    result = GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.prompt.startswith("<tables_json>")
    assert client.request.response_schema_name == "granite_retail_order.v1"
    assert client.request.response_json_schema is not None
    line_items = client.request.response_json_schema["properties"]["line_items"]
    assert line_items["maxItems"] == 40
    item_properties = line_items["items"]["properties"]
    assert "source_text" in item_properties
    assert result.normalization_json["regionEnvelope"]["resolved_document_type"] == "retail_order"
    assert (
        result.normalization_json["regionEnvelope"]["model_output_schema_name"]
        == "granite_retail_order.v1"
    )


def test_granite_gateway_routes_service_record_tables_to_service_record_schema() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="service_record_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        expected_fields=("service_description", "labor_operation", "line_total"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.prompt.startswith("<tables_json>")
    assert "Do not include source_text" in client.request.prompt
    assert client.request.response_schema_name == "granite_service_record_line_items.v1"
    assert client.request.response_json_schema is not None
    assert client.request.response_json_schema["required"] == ["line_items"]
    item_properties = client.request.response_json_schema["properties"]["line_items"]["items"][
        "properties"
    ]
    assert "source_text" not in item_properties


def test_granite_gateway_renders_docling_table_json_as_readable_rows() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    table_id = uuid4()
    source.tables.append(
        ParsedTableText(
            table_id=table_id,
            page_number=1,
            table_index=1,
            table_json={
                "data": {
                    "grid": [
                        [
                            {"text": "DESCRIPTION OF SERVICE AND PARTS"},
                            {"text": "AMOUNT"},
                        ],
                        [
                            {"text": "600 mile running-in check"},
                            {"text": "$250.00"},
                        ],
                    ]
                }
            },
        )
    )
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="service_record_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        expected_fields=("service_description", "line_total"),
        grounding=SemanticGroundingRef(kind="table", table_id=table_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.prompt.startswith("<tables_json>")
    assert "DESCRIPTION OF SERVICE AND PARTS | AMOUNT" in client.request.prompt
    assert "600 mile running-in check | $250.00" in client.request.prompt
    assert '"bbox"' not in client.request.prompt


def test_granite_gateway_table_schema_allows_docling_row_identity() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    table_id = uuid4()
    source.tables.append(
        ParsedTableText(
            table_id=table_id,
            page_number=1,
            table_index=1,
            table_json={
                "data": {
                    "grid": [
                        [{"text": "Description"}, {"text": "Amount"}],
                        [{"text": "Consultation"}, {"text": "$120.00"}],
                    ]
                }
            },
        )
    )
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("description", "amount"),
        grounding=SemanticGroundingRef(kind="table", table_id=table_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert "row_index=1: Consultation | $120.00" in client.request.prompt
    assert client.request.response_json_schema is not None
    line_item_properties = client.request.response_json_schema["properties"]["line_items"]["items"][
        "properties"
    ]
    assert {"row_index", "table_id", "page_number"}.issubset(line_item_properties)


def test_granite_gateway_routes_title_seller_info_to_observation_schema() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="seller_information_block",
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=("seller_name", "property_address"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.response_schema_name == "granite_real_estate_title_seller_info.v1"
    assert "seller_name" in client.request.prompt
    assert '"seller_name":null' in client.request.prompt
    assert '"fields":[{"name":"seller_name"' not in client.request.prompt


def test_granite_gateway_uses_receipt_line_item_budget() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="receipt_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        expected_fields=("item_description", "quantity", "line_total"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.max_output_tokens == 2048
    assert client.request.timeout_seconds == 90


def test_granite_gateway_uses_larger_retail_order_line_item_budget() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="retail_order_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        expected_fields=(
            "item_description",
            "quantity",
            "line_total",
            "sku",
            "price",
            "salesperson_code",
            "instant_savings",
        ),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        metadata={"resolved_document_type": "retail_order"},
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.response_schema_name == "granite_retail_order.v1"
    assert client.request.max_output_tokens == 4096
    assert client.request.timeout_seconds == 120


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

    class TruncatingRetailClient:
        def __init__(self) -> None:
            self.requests: list[VisionGenerateRequest] = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            if len(self.requests) == 1:
                raise ModelProtocolError(
                    "Vision model response was truncated before valid JSON completed.",
                    details={"finish_reason": "length"},
                )
            return VisionGenerateResponse(
                profile_name=GRANITE_VISION_PROFILE,
                model_name="fake-granite",
                model_version="test",
                source_engine="granite_vision_3b",
                prompt_version=request.prompt_version,
                raw_text="{}",
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
                confidence_json={},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = TruncatingRetailClient()

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


def test_granite_gateway_uses_schema_backed_observation_budget() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="dispute_reason_block",
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=("merchant", "amount", "dispute_reason"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.max_output_tokens == 2048
    assert client.request.timeout_seconds == 75


def test_granite_gateway_uses_general_observation_budget() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="document_footer",
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=("visible_labels",),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.max_output_tokens == 768
    assert client.request.timeout_seconds == 45


def test_granite_observation_prompt_is_bounded() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="dispute_reason_block",
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=("transaction_date", "merchant", "amount", "dispute_reason"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert "Extract only the requested observation fields" in client.request.prompt
    assert "Do not transcribe paragraphs" in client.request.prompt
    assert "Return null or an empty list when evidence is not visible" in client.request.prompt
    assert "the API response schema wins" in client.request.prompt
    assert "do not place extracted facts inside confidence" in client.request.prompt


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
