from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from lib.extraction.models import ExtractionSourceDocument, ParsedElementText, ParsedPageText
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import QWEN_SEMANTIC_HQ_PROFILE, QWEN_SEMANTIC_PROFILE
from lib.semantic_annotations import qwen_gateway
from lib.semantic_annotations.fixture_gateway import FixtureSemanticAnnotationGateway
from lib.semantic_annotations.qwen_gateway import QwenSemanticAnnotationGateway
from lib.semantic_annotations.schema import semantic_annotation_model_output_schema


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
    assert client.request.response_schema_name == "semantic_annotation_model_output"
    assert client.request.response_json_schema == semantic_annotation_model_output_schema()
    assert result.manifest.manifest["schema_name"] == "semantic_annotation_manifest"
    assert result.manifest.confidence["overall"] == 0.88


def test_live_qwen_gateway_prompt_keeps_semantic_planning_but_not_tiny_region_limits() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=_semantic_payload(source.pages[0].page_id),
    )

    QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert client.request is not None
    prompt = client.request.prompt
    assert "Return valid JSON only" in prompt
    assert "Docling is the physical parse authority" in prompt
    assert "semantic planning, not extraction" in prompt
    assert "expected_fields must contain field names only" in prompt
    assert "Return no more than 6 regions total" in prompt
    assert "do not enumerate every visible field" in prompt
    assert "compact semantic scout JSON" in prompt
    assert "canonical semantic manifest" not in prompt
    assert "at most two regions total" not in prompt
    assert "max_output_tokens" not in prompt


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
    assert client.request is not None
    assert client.request.timeout_seconds == 180
    assert client.request.max_output_tokens == 4096
    assert client.request.response_schema_name == "semantic_annotation_model_output"
    assert client.request.response_json_schema is None


def test_live_qwen_high_quality_gateway_normalizes_page_annotations_shape() -> None:
    source = _source_with_page_image_and_element()
    page = source.pages[0]
    element = source.elements[0]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json={
            "page_annotations": [
                {
                    "page_id": str(page.page_id),
                    "regions": [
                        {
                            "element_id": str(element.element_id),
                            "granite_task": "kvp",
                            "target_schema": "medical_eob",
                            "expected_fields": ["request_status"],
                            "reason": "This block identifies the denial decision.",
                            "confidence": 0.95,
                            "needs_high_quality_pass": False,
                        }
                    ],
                }
            ]
        },
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert len(result.manifest.pages) == 1
    assert result.manifest.pages[0].page_id == page.page_id
    assert result.manifest.pages[0].page_number == page.page_number
    assert len(result.manifest.regions) == 1
    region = result.manifest.regions[0]
    assert region.grounding.kind == "element"
    assert region.grounding.element_id == element.element_id
    assert region.granite_task == "kvp"
    assert region.target_schema == "medical_eob"
    assert region.expected_fields == ("request_status",)


def test_live_qwen_high_quality_gateway_caps_alternate_page_annotation_regions() -> None:
    source = _source_with_page_image_and_element()
    page = source.pages[0]
    element = source.elements[0]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json={
            "page_annotations": [
                {
                    "page_id": str(page.page_id),
                    "regions": [
                        {
                            "element_id": str(element.element_id),
                            "granite_task": "kvp",
                            "target_schema": "medical_eob",
                            "expected_fields": [f"field_{index}"],
                            "reason": f"Region {index}.",
                            "confidence": 0.9 - (index * 0.01),
                        }
                        for index in range(8)
                    ],
                }
            ]
        },
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert len(result.manifest.regions) == 6
    assert result.manifest.regions[0].expected_fields == ("field_0",)


def test_live_qwen_high_quality_gateway_normalizes_single_page_wrapper_shape() -> None:
    source = _source_with_page_image_and_element()
    page = source.pages[0]
    element = source.elements[0]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json={
            "page": {
                "pageId": str(page.page_id),
                "granite_task": "kvp",
                "target_schema": "medical_eob",
                "regions": [
                    {
                        "elementId": str(element.element_id),
                        "expected_fields": [f"deadline_field_{index}"],
                        "reason": "Contains the 180-day grievance deadline.",
                        "confidence": 0.9,
                    }
                    for index in range(9)
                ],
            }
        },
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert len(result.manifest.regions) == 6
    region = result.manifest.regions[0]
    assert region.grounding.kind == "element"
    assert region.grounding.element_id == element.element_id
    assert region.granite_task == "kvp"
    assert region.target_schema == "medical_eob"
    assert region.expected_fields == ("deadline_field_0",)


def test_live_qwen_high_quality_gateway_normalizes_nested_pages_shape() -> None:
    source = _source_with_page_image()
    page = source.pages[0]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json={
            "pages": [
                {
                    "page_id": str(page.page_id),
                    "regions": [
                        {
                            "granite_task": "kvp",
                            "target_schema": "medical_eob",
                            "expected_fields": [],
                            "confidence": 0.1,
                            "reason": "low_text_density, no OCR text, no visible fields",
                            "needs_high_quality_pass": True,
                            "review_required": True,
                            "unmatched_region": True,
                        }
                    ],
                }
            ]
        },
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert result.manifest.pages[0].page_id == page.page_id
    assert len(result.manifest.regions) == 1
    region = result.manifest.regions[0]
    assert region.semantic_type == "unmatched_region"
    assert region.granite_task == "ignore"
    assert region.review_required is True


def test_live_qwen_high_quality_gateway_repairs_unknown_single_chunk_page_id() -> None:
    source = _source_with_page_image_and_element()
    page = source.pages[0]
    element = source.elements[0]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json={
            "page_annotations": [
                {
                    "page_id": str(uuid4()),
                    "regions": [
                        {
                            "element_id": str(element.element_id),
                            "granite_task": "kvp",
                            "target_schema": "medical_eob",
                            "expected_fields": ["request_status"],
                            "confidence": 0.8,
                        }
                    ],
                }
            ]
        },
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert result.manifest.pages[0].page_id == page.page_id
    assert result.manifest.pages[0].escalation_required is True
    manifest_pages = result.manifest.manifest["pages"]
    assert isinstance(manifest_pages, list)
    manifest_page = manifest_pages[0]
    assert isinstance(manifest_page, dict)
    assert "missing_docling_grounding" in manifest_page["escalation_reasons"]


def test_live_qwen_high_quality_gateway_merges_duplicate_page_annotations() -> None:
    source = _source_with_page_image_and_element()
    page = source.pages[0]
    element = source.elements[0]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json={
            "page_annotations": [
                {
                    "page_id": str(page.page_id),
                    "regions": [
                        {
                            "element_id": str(element.element_id),
                            "granite_task": "kvp",
                            "target_schema": "medical_eob",
                            "expected_fields": ["request_status"],
                            "confidence": 0.8,
                        }
                    ],
                },
                {
                    "page_id": str(page.page_id),
                    "regions": [
                        {
                            "element_id": str(element.element_id),
                            "granite_task": "kvp",
                            "target_schema": "medical_eob",
                            "expected_fields": ["reference_number"],
                            "confidence": 0.7,
                        }
                    ],
                },
            ]
        },
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert len(result.manifest.pages) == 1
    assert result.manifest.pages[0].page_id == page.page_id
    assert {region.expected_fields for region in result.manifest.regions} == {
        ("request_status",),
        ("reference_number",),
    }


def test_live_qwen_smart_gateway_chunks_pages_for_one_image_semantic_service() -> None:
    source = _source_with_two_page_images()
    page_by_hash = {page.image_sha256: page.page_id for page in source.pages if page.image_sha256}

    class ChunkingClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            image_hash = request.image_inputs[0].validated_sha256()
            page_id = page_by_hash[image_hash]
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_2b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload(page_id),
                confidence_json={"overall": 0.8},
                input_sha256=(image_hash,),
                latency_ms=1,
            )

    client = ChunkingClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="smart",
    )

    assert len(client.requests) == 2
    assert [len(request.image_inputs) for request in client.requests] == [1, 1]
    assert len(result.manifest.pages) == 2
    assert len(result.manifest.regions) == 2
    assert result.manifest.confidence["chunk_count"] == 2


def test_live_qwen_high_quality_gateway_chunks_pages_for_one_image_hq_service() -> None:
    source = _source_with_two_page_images()
    page_by_hash = {page.image_sha256: page.page_id for page in source.pages if page.image_sha256}

    class ChunkingClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            image_hash = request.image_inputs[0].validated_sha256()
            page_id = page_by_hash[image_hash]
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_HQ_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload(page_id),
                confidence_json={"overall": 0.82},
                input_sha256=(image_hash,),
                latency_ms=1,
            )

    client = ChunkingClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert len(client.requests) == 2
    assert [len(request.image_inputs) for request in client.requests] == [1, 1]
    assert len(result.manifest.pages) == 2
    assert result.manifest.profile_name == QWEN_SEMANTIC_HQ_PROFILE
    assert result.manifest.confidence["chunk_count"] == 2


def test_live_qwen_gateway_rejects_malformed_model_output() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json={"pages": [], "regions": [{"semantic_type": "not_allowed"}]},
    )

    with pytest.raises(ModelProtocolError, match="semantic"):
        QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")


def test_live_qwen_gateway_rejects_schema_invalid_value_bearing_output() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["value"] = "$42.00"
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=payload,
    )

    with pytest.raises(ModelProtocolError, match="schema"):
        QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")


def test_live_qwen_gateway_drops_invalid_expected_field_names_from_model_output() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["expected_fields"] = ["total_amount", "page_rolе"]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert result.manifest.regions[0].expected_fields == ("total_amount",)
    persisted_regions = result.manifest.manifest["regions"]
    assert isinstance(persisted_regions, list)
    persisted_region = persisted_regions[0]
    assert isinstance(persisted_region, dict)
    assert persisted_region["expected_fields"] == ["total_amount"]


def test_live_qwen_gateway_marks_unknown_docling_grounding_review_required() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["grounding"] = {
        "kind": "element",
        "page_id": None,
        "element_id": str(uuid4()),
        "table_id": None,
    }
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    repaired_region = result.manifest.regions[0]
    assert repaired_region.semantic_type == "unmatched_region"
    assert repaired_region.grounding.kind == "unmatched_region"
    assert repaired_region.review_required is True
    assert repaired_region.confidence == 0.2


def test_live_qwen_gateway_clears_extraneous_grounding_ids() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["grounding"] = {
        "kind": "page",
        "page_id": str(source.pages[0].page_id),
        "element_id": str(uuid4()),
        "table_id": None,
    }
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    repaired_grounding = result.manifest.regions[0].grounding
    assert repaired_grounding.kind == "page"
    assert repaired_grounding.page_id == source.pages[0].page_id
    assert repaired_grounding.element_id is None
    assert repaired_grounding.table_id is None


def test_live_qwen_gateway_deduplicates_duplicate_model_regions() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    regions.append(dict(regions[0]))
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert len(result.manifest.regions) == 1
    persisted_regions = result.manifest.manifest["regions"]
    assert isinstance(persisted_regions, list)
    assert len(persisted_regions) == 1


def test_live_qwen_gateway_retries_once_after_truncated_model_output() -> None:
    source = _source_with_page_image()

    class FlakyClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            if len(self.requests) == 1:
                raise ModelProtocolError("Vision model response was truncated.")
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_2b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload(source.pages[0].page_id),
                confidence_json={"overall": 0.8},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = FlakyClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert result.manifest.pages[0].page_id == source.pages[0].page_id
    assert len(client.requests) == 2


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
        "schema_name": "semantic_annotation_model_output",
        "schema_version": "v1",
        "document_type": "invoice",
        "pages": [
            {
                "page_id": str(page_id),
                "page_number": 1,
                "page_role": "payment_summary",
                "document_type_hint": "invoice",
                "extraction_usefulness": "high",
                "is_boilerplate": False,
                "has_structured_targets": True,
                "ambiguous": False,
                "escalation_required": False,
                "escalation_reasons": [],
                "reason": "Invoice summary and totals are visible.",
                "confidence": 0.91,
            }
        ],
        "regions": [
            {
                "semantic_type": "billing_summary",
                "priority": "high",
                "granite_task": "kvp",
                "target_schema": "invoice",
                "expected_fields": ["total_amount"],
                "grounding": {
                    "kind": "page",
                    "page_id": str(page_id),
                    "element_id": None,
                    "table_id": None,
                },
                "review_required": False,
                "reason": "Top of the page contains invoice totals.",
                "confidence": 0.89,
            }
        ],
        "quality_flags": {"needs_high_quality_pass": False, "visual_degradation": False},
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


def _source_with_page_image_and_element() -> ExtractionSourceDocument:
    source = _source_with_page_image()
    return ExtractionSourceDocument(
        document_id=source.document_id,
        household_id=source.household_id,
        title=source.title,
        original_filename=source.original_filename,
        mime_type=source.mime_type,
        family="medical_eob",
        subtype=source.subtype,
        sensitivity=source.sensitivity,
        document_date=source.document_date,
        counterparty_display=source.counterparty_display,
        primary_folder_id=source.primary_folder_id,
        metadata=source.metadata,
        pages=source.pages,
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=source.pages[0].page_number,
                ordinal=1,
                text="Denied outpatient request",
                bbox=None,
            )
        ],
        tables=source.tables,
    )


def _source_with_two_page_images() -> ExtractionSourceDocument:
    first_page = uuid4()
    second_page = uuid4()
    first_sha = hashlib.sha256(b"page-one").hexdigest()
    second_sha = hashlib.sha256(b"page-two").hexdigest()
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Two page invoice",
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
                page_id=first_page,
                page_number=1,
                text="Invoice cover",
                image_bytes=b"page-one",
                image_mime_type="image/png",
                image_sha256=first_sha,
            ),
            ParsedPageText(
                page_id=second_page,
                page_number=2,
                text="Invoice total $42",
                image_bytes=b"page-two",
                image_mime_type="image/png",
                image_sha256=second_sha,
            ),
        ],
        elements=[],
        tables=[],
    )
