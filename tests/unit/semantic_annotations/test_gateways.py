from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
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


def test_fixture_gateway_infers_target_family_from_generic_docling_text() -> None:
    source = _source_with_page_image()
    source = replace(
        source,
        title="Uploaded document",
        original_filename="uploaded.pdf",
        family="generic",
        pages=[
            replace(
                source.pages[0],
                text=(
                    "Seller: Acme Repairs\n"
                    "Invoice Number: INV-4242\n"
                    "Issue Date: 2026-04-01\n"
                    "Total: 1042.15\n"
                ),
            )
        ],
    )

    result = FixtureSemanticAnnotationGateway().annotate(source, quality_mode="smart")

    assert result.manifest.manifest["document_type"] == "invoice"
    assert result.manifest.pages[0].document_type_hint == "invoice"
    assert result.manifest.pages[0].has_structured_targets is True
    assert result.manifest.regions[0].semantic_type == "billing_summary"
    assert result.manifest.regions[0].target_schema == "invoice"


def test_live_qwen_smart_gateway_builds_truthful_qwen3_vl_8b_manifest() -> None:
    source = _source_with_page_image_and_element()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=_semantic_payload(source.pages[0].page_id),
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert result.manifest.source_engine == "qwen3_vl_8b"
    assert result.manifest.profile_name == QWEN_SEMANTIC_PROFILE
    assert result.manifest.prompt_version == "phase8_5-semantic-smart-v3"
    assert client.request is not None
    assert "Docling context" in client.request.prompt
    assert '"focusPages":' in client.request.prompt
    context_json = client.request.prompt.split("Docling context: ", 1)[1]
    assert '": ' not in context_json
    assert ', "' not in context_json
    prompt_context = json.loads(context_json)
    assert "pages" not in prompt_context
    assert "imageSha256" not in prompt_context["focusPages"][0]
    assert "bbox" not in prompt_context["focusPages"][0]["elements"][0]
    assert client.request.image_inputs[0].content == b"page-image"
    assert client.request.response_schema_name == "semantic_annotation_model_output"
    assert client.request.response_json_schema == semantic_annotation_model_output_schema()
    assert client.request.timeout_seconds == 300
    assert result.manifest.manifest["schema_name"] == "semantic_annotation_manifest"
    assert result.manifest.confidence["overall"] == 0.88


def test_live_qwen_gateway_prompt_keeps_semantic_planning_but_not_tiny_region_limits() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=_semantic_payload(source.pages[0].page_id),
    )

    QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert client.request is not None
    prompt = client.request.prompt
    assert "Return valid JSON only" in prompt
    assert "Docling page_id, element_id, and table_id" in prompt
    assert "semantic document-understanding layer" in prompt
    assert "semantic inventory and extraction intent, not canonical extraction" in prompt
    assert "Inspect layout, table structure, visual grouping" in prompt
    assert "expected_fields must contain field names only" in prompt
    assert "Emit all materially extractable regions" in prompt
    assert "Use no more than 12 regions total" in prompt
    assert "Return no more than 6 regions total" not in prompt
    assert "highest-value Granite routing targets" not in prompt
    assert "do not enumerate every visible field" not in prompt
    assert "generic observations" in prompt
    assert "Do not force unfamiliar documents into invoice, receipt, or medical_eob" in prompt
    assert "semantic_annotation_model_output JSON" in prompt
    assert "canonical semantic manifest" not in prompt
    assert "at most two regions total" not in prompt
    assert "max_output_tokens" not in prompt


def test_live_qwen_smart_gateway_uses_compact_output_budget_for_16k_service() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=_semantic_payload(source.pages[0].page_id),
    )

    QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert client.request is not None
    assert client.request.max_output_tokens == 6144


def test_live_qwen_high_quality_gateway_uses_high_quality_prompt_version() -> None:
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
    assert client.request.profile_name == QWEN_SEMANTIC_PROFILE
    assert client.request.timeout_seconds == 300
    assert client.request.max_output_tokens == 6144
    assert client.request.response_schema_name == "semantic_annotation_model_output"
    assert client.request.response_json_schema is not None


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
                            "needs_human_review": False,
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
    assert region.grounding.page_id == page.page_id
    assert region.grounding.element_id == element.element_id
    assert region.granite_task == "kvp"
    assert region.target_schema == "medical_eob"
    assert region.expected_fields == ("request_status",)


def test_live_qwen_gateway_maps_legacy_hq_flag_to_review_without_manifest_leak() -> None:
    source = _source_with_page_image_and_element()
    page = source.pages[0]
    element = source.elements[0]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
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
                            "confidence": 0.61,
                            "needs_high_quality_pass": True,
                        }
                    ],
                }
            ]
        },
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    quality_flags = result.manifest.manifest["quality_flags"]
    assert quality_flags["needs_human_review"] is True
    assert "needs_high_quality_pass" not in quality_flags
    assert result.manifest.regions[0].review_required is True
    assert (
        result.manifest.confidence["normalization"][
            "legacy_needs_high_quality_pass_mapped_to_review"
        ]
        == 1
    )


def test_live_qwen_gateway_resolves_stable_docling_refs_to_persisted_ids() -> None:
    source = _source_with_page_image_and_element()
    page = source.pages[0]
    element = source.elements[0]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json={
            "schema_name": "semantic_annotation_model_output",
            "schema_version": "v1",
            "document_type": "medical_eob",
            "pages": [
                {
                    "page_id": "page-1",
                    "page_number": 1,
                    "page_role": "denial_or_decision",
                    "document_type_hint": "medical_eob",
                    "extraction_usefulness": "high",
                    "is_boilerplate": False,
                    "has_structured_targets": True,
                    "ambiguous": False,
                    "escalation_required": False,
                    "escalation_reasons": [],
                    "reason": "Contains denial status.",
                    "confidence": 0.9,
                }
            ],
            "regions": [
                {
                    "semantic_type": "denial_or_coverage_decision",
                    "priority": "high",
                    "granite_task": "kvp",
                    "target_schema": "medical_eob",
                    "expected_fields": ["request_status"],
                    "grounding": {
                        "kind": "element",
                        "page_id": "page-1",
                        "element_id": "page-1-element-1",
                        "table_id": None,
                    },
                    "review_required": False,
                    "reason": "This block identifies the denial decision.",
                    "confidence": 0.95,
                }
            ],
            "quality_flags": {
                "needs_human_review": False,
                "visual_degradation": False,
                "poor_ocr": False,
                "ambiguous_document_type": False,
                "reason": None,
            },
        },
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert result.manifest.pages[0].page_id == page.page_id
    region = result.manifest.regions[0]
    assert region.grounding.page_id == page.page_id
    assert region.grounding.element_id == element.element_id
    assert result.manifest.manifest["pages"][0]["page_id"] == str(page.page_id)
    assert result.manifest.manifest["regions"][0]["grounding"]["element_id"] == str(
        element.element_id
    )
    assert result.manifest.confidence["normalization"]["stable_docling_refs_resolved"] == 3


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

    assert len(result.manifest.regions) == 8
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

    assert len(result.manifest.regions) == 9
    region = result.manifest.regions[0]
    assert region.grounding.kind == "element"
    assert region.grounding.element_id == element.element_id
    assert region.granite_task == "kvp"
    assert region.target_schema == "medical_eob"
    assert region.expected_fields == ("deadline_field_0",)


def test_live_qwen_gateway_preserves_planner_metadata_in_manifest() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    pages = payload["pages"]
    assert isinstance(pages, list)
    page = pages[0]
    assert isinstance(page, dict)
    page.update(
        {
            "page_family_hints": ["invoice", "receipt"],
            "continuation_group": "service-lines",
            "docling_table_signal": "weak",
            "requires_cross_page_context": False,
            "material_region_count_hint": 0,
        }
    )
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region.update(
        {
            "importance": "critical",
            "source_signal": "mixed",
            "coverage_role": "primary",
            "extraction_scope": "page",
            "requires_full_page_image": False,
            "continuation_group": "service-lines",
            "must_extract_reason": "Visible total region.",
            "negative_routing_reason": "Not a medical EOB.",
            "min_expected_items": 0,
            "visual_bbox_hint": {"x1": 0, "y1": 0, "x2": 1000, "y2": 500},
        }
    )
    payload["document_type_candidates"] = [
        {
            "document_type": "invoice",
            "confidence": 0.9,
            "evidence_terms": ["invoice"],
            "reason": "invoice anchor present",
        }
    ]
    payload["planner_notes"] = ["Docling table text is weak; use full page image."]
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    page_annotation = result.manifest.pages[0]
    assert page_annotation.metadata["requires_cross_page_context"] is False
    assert page_annotation.metadata["material_region_count_hint"] == 0
    persisted_page = result.manifest.manifest["pages"][0]
    assert isinstance(persisted_page, dict)
    assert persisted_page["requires_cross_page_context"] is False
    assert persisted_page["material_region_count_hint"] == 0
    region_annotation = result.manifest.regions[0]
    assert region_annotation.metadata["requires_full_page_image"] is False
    assert region_annotation.metadata["min_expected_items"] == 0
    persisted_region = result.manifest.manifest["regions"][0]
    assert isinstance(persisted_region, dict)
    assert persisted_region["importance"] == "critical"
    assert persisted_region["requires_full_page_image"] is False
    assert persisted_region["min_expected_items"] == 0
    assert result.manifest.manifest["document_type_candidates"]
    assert result.manifest.manifest["planner_notes"] == [
        "Docling table text is weak; use full page image."
    ]


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
                            "needs_human_review": True,
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


def test_live_qwen_smart_gateway_uses_four_image_qwen3_vl_8b_fan_in() -> None:
    source = _source_with_two_page_images()
    page_by_hash = {page.image_sha256: page.page_id for page in source.pages if page.image_sha256}

    class ChunkingClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            page_ids = [page_by_hash[image.validated_sha256()] for image in request.image_inputs]
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload_for_pages(page_ids),
                confidence_json={"overall": 0.8},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = ChunkingClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="smart",
    )

    assert len(client.requests) == 1
    assert [len(request.image_inputs) for request in client.requests] == [2]
    assert len(result.manifest.pages) == 2
    assert len(result.manifest.regions) == 2
    assert result.manifest.profile_name == QWEN_SEMANTIC_PROFILE
    assert "chunk_count" not in result.manifest.confidence
    prompt_contexts = [_docling_context_from_prompt(request.prompt) for request in client.requests]
    assert [context["document"]["pageCount"] for context in prompt_contexts] == [2]
    assert [
        [page["pageNumber"] for page in context["focusPages"]] for context in prompt_contexts
    ] == [[1, 2]]
    assert all("Invoice cover" in request.prompt for request in client.requests)
    assert all("Invoice total $42" in request.prompt for request in client.requests)


def test_live_qwen_smart_gateway_rejects_coverage_failure_without_one_page_fallback() -> None:
    source = _source_with_two_page_images()
    page_by_hash = {page.image_sha256: page.page_id for page in source.pages if page.image_sha256}

    class CoverageFailureClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            page_ids = [page_by_hash[image.validated_sha256()] for image in request.image_inputs]
            if len(request.image_inputs) > 1:
                page_ids = page_ids[:1]
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload_for_pages(page_ids),
                confidence_json={"overall": 0.8},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = CoverageFailureClient()

    with pytest.raises(ModelProtocolError, match="page coverage"):
        QwenSemanticAnnotationGateway(client=client).annotate(
            source,
            quality_mode="smart",
        )

    assert [len(request.image_inputs) for request in client.requests] == [2]


def test_live_qwen_smart_gateway_fills_missing_blank_focus_page_without_fallback() -> None:
    source = _source_with_blank_second_page()

    class MissingBlankPageClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload_for_pages([source.pages[0].page_id]),
                confidence_json={"overall": 0.8},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = MissingBlankPageClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="smart",
    )

    assert [len(request.image_inputs) for request in client.requests] == [2]
    assert [page.page_id for page in result.manifest.pages] == [
        source.pages[0].page_id,
        source.pages[1].page_id,
    ]
    assert result.manifest.pages[1].extraction_usefulness == "none"
    assert result.manifest.pages[1].is_boilerplate is True
    assert result.manifest.pages[1].has_structured_targets is False
    assert result.manifest.pages[1].reason == (
        "Docling reported a blank/no-signal focus page omitted by the model."
    )
    assert result.manifest.confidence["normalization"] == {
        "output_scope_filter_policy": "filter_to_requested_docling_pages",
        "missing_blank_focus_pages_filled": 1,
        "missing_blank_focus_page_ids": [str(source.pages[1].page_id)],
        "missing_blank_focus_page_policy": "fill_no_extraction_target_page_only",
    }


def test_live_qwen_smart_gateway_rejects_context_length_without_one_page_fallback() -> None:
    source = _source_with_two_page_images()

    class ContextLengthFailureClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            if len(request.image_inputs) > 1:
                raise ModelProtocolError(
                    "This model's maximum context length is 32768 tokens. "
                    "However, you requested 6144 output tokens and your prompt contains "
                    "at least 14500 input tokens."
                )
            raise AssertionError("Unexpected one-page fallback request.")

    client = ContextLengthFailureClient()

    with pytest.raises(ModelProtocolError, match="maximum context length"):
        QwenSemanticAnnotationGateway(client=client).annotate(
            source,
            quality_mode="smart",
        )

    assert [len(request.image_inputs) for request in client.requests] == [2]


def test_live_qwen_smart_gateway_rejects_truncation_without_one_page_fallback() -> None:
    source = _source_with_two_page_images()

    class TruncationFailureClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            if len(request.image_inputs) > 1:
                raise ModelProtocolError(
                    "Vision model response was truncated before valid JSON completed."
                )
            raise AssertionError("Unexpected one-page fallback request.")

    client = TruncationFailureClient()

    with pytest.raises(ModelProtocolError, match="truncated"):
        QwenSemanticAnnotationGateway(client=client).annotate(
            source,
            quality_mode="smart",
        )

    assert [len(request.image_inputs) for request in client.requests] == [2, 2]


def test_live_qwen_smart_gateway_filters_context_only_pages_inside_requested_window() -> None:
    source = _source_with_two_page_images()
    all_page_ids = [page.page_id for page in source.pages]

    class ContextOnlyPageClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload_for_pages(all_page_ids),
                confidence_json={"overall": 0.8},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = ContextOnlyPageClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="smart",
    )

    assert [len(request.image_inputs) for request in client.requests] == [2]
    assert [page.page_id for page in result.manifest.pages] == all_page_ids
    assert [region.grounding.page_id for region in result.manifest.regions] == all_page_ids


def test_live_qwen_smart_gateway_chunks_long_documents_without_one_page_fallback() -> None:
    source = _source_with_many_page_images(5)
    page_by_hash = {page.image_sha256: page.page_id for page in source.pages if page.image_sha256}

    class WindowChunkClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            page_ids = [page_by_hash[image.validated_sha256()] for image in request.image_inputs]
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload_for_pages(page_ids),
                confidence_json={"overall": 0.8},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = WindowChunkClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="smart",
    )

    assert [len(request.image_inputs) for request in client.requests] == [4, 1]
    assert len(result.manifest.pages) == 5
    assert "fallback_reason" not in result.manifest.confidence


def test_live_qwen_high_quality_gateway_uses_active_semantic_fan_in() -> None:
    source = _source_with_two_page_images()
    page_by_hash = {page.image_sha256: page.page_id for page in source.pages if page.image_sha256}

    class ChunkingClient:
        requests: list[VisionGenerateRequest]

        def __init__(self) -> None:
            self.requests = []

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.requests.append(request)
            page_ids = [
                page_by_hash[image.validated_sha256()]
                for image in request.image_inputs
                if image.validated_sha256() in page_by_hash
            ]
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_HQ_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload_for_pages(page_ids),
                confidence_json={"overall": 0.82},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = ChunkingClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    assert len(client.requests) == 1
    assert [len(request.image_inputs) for request in client.requests] == [2]
    assert len(result.manifest.pages) == 2
    assert result.manifest.profile_name == QWEN_SEMANTIC_HQ_PROFILE
    assert "chunk_count" not in result.manifest.confidence


def test_live_qwen_gateway_rejects_malformed_model_output() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
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
        source_engine="qwen3_vl_8b",
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
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert result.manifest.regions[0].expected_fields == ("total_amount",)
    persisted_regions = result.manifest.manifest["regions"]
    assert isinstance(persisted_regions, list)
    persisted_region = persisted_regions[0]
    assert isinstance(persisted_region, dict)
    assert persisted_region["expected_fields"] == ["total_amount"]


def test_live_qwen_gateway_repairs_missing_target_schema_from_qwen_document_type() -> None:
    source = replace(
        _source_with_page_image_and_element(),
        metadata={"phase4": {"classification": {"family": "medical_eob"}}},
    )
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["target_schema"] = None
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    repaired_region = result.manifest.regions[0]
    assert repaired_region.target_schema == "invoice"
    assert repaired_region.review_required is True


def test_live_qwen_gateway_does_not_fall_back_to_phase4_when_qwen_document_type_is_absent() -> None:
    source = replace(
        _source_with_page_image_and_element(),
        metadata={"phase4": {"classification": {"family": "medical_eob"}}},
    )
    payload = _semantic_payload(source.pages[0].page_id)
    payload["document_type"] = "unknown"
    pages = payload["pages"]
    assert isinstance(pages, list)
    page = pages[0]
    assert isinstance(page, dict)
    page["document_type_hint"] = None
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["target_schema"] = None
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_HQ_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(
        source,
        quality_mode="high_quality",
    )

    repaired_region = result.manifest.regions[0]
    assert repaired_region.target_schema is None
    assert repaired_region.review_required is True


def test_live_qwen_gateway_realigns_wrong_target_schema_to_source_family() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["target_schema"] = "medical_eob"
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    repaired_region = result.manifest.regions[0]
    assert repaired_region.target_schema == "invoice"
    assert repaired_region.review_required is True
    assert repaired_region.confidence == 0.2
    assert repaired_region.metadata["original_target_schema"] == "medical_eob"
    assert repaired_region.metadata["target_schema_repaired"] is True


def test_live_qwen_gateway_uses_document_type_hint_before_unclassified_family() -> None:
    source = replace(_source_with_page_image(), family="medical_eob", metadata={})
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["semantic_type"] = "invoice_line_item_table"
    region["target_schema"] = "medical_eob"
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    repaired_region = result.manifest.regions[0]
    assert repaired_region.target_schema == "invoice"
    assert repaired_region.metadata["original_target_schema"] == "medical_eob"
    assert repaired_region.metadata["target_schema_repaired"] is True


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
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    repaired_region = result.manifest.regions[0]
    assert repaired_region.semantic_type == "unmatched_region"
    assert repaired_region.grounding.kind == "unmatched_region"
    assert repaired_region.review_required is True
    assert repaired_region.confidence == 0.2


def test_live_qwen_gateway_marks_malformed_grounding_uuid_review_required() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["grounding"] = {
        "kind": "element",
        "page_id": None,
        "element_id": "element-3",
        "table_id": None,
    }
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
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
        source_engine="qwen3_vl_8b",
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
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert len(result.manifest.regions) == 1
    persisted_regions = result.manifest.manifest["regions"]
    assert isinstance(persisted_regions, list)
    assert len(persisted_regions) == 1


def test_live_qwen_smart_gateway_collapses_duplicate_canonical_page_annotations_with_audit() -> (
    None
):
    source = _source_with_page_image()
    page_id = source.pages[0].page_id
    payload = _semantic_payload(page_id)
    pages = payload["pages"]
    assert isinstance(pages, list)
    pages.append(dict(pages[0]))
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert len(result.manifest.pages) == 1
    persisted_pages = result.manifest.manifest["pages"]
    assert isinstance(persisted_pages, list)
    assert len(persisted_pages) == 1
    normalization = result.manifest.confidence["normalization"]
    assert normalization == {
        "duplicate_page_annotations_collapsed": 1,
        "duplicate_page_annotation_page_ids": [str(page_id)],
        "duplicate_page_annotation_policy": "merge_by_page_id_preserving_docling_coverage",
    }
    assert result.manifest.pages[0].metadata["normalization"] == normalization


def test_live_qwen_gateway_does_not_inject_service_record_semantic_intent() -> None:
    source = _source_with_page_image()
    page_id = source.pages[0].page_id
    payload = _semantic_payload(page_id)
    payload["document_type"] = "service_record"
    pages = payload["pages"]
    assert isinstance(pages, list)
    page = pages[0]
    assert isinstance(page, dict)
    page["document_type_hint"] = "service_record"
    page["docling_table_signal"] = "weak"
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region.update(
        {
            "semantic_type": "service_record_line_item_table",
            "granite_task": "tables_json",
            "target_schema": "receipt",
            "source_signal": "mixed",
            "requires_full_page_image": False,
        }
    )
    region.pop("continuation_group", None)
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_8b",
        normalized_json=payload,
    )

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    region_result = result.manifest.regions[0]
    assert region_result.semantic_type == "service_record_line_item_table"
    assert region_result.target_schema == "receipt"
    assert "continuation_group" not in region_result.metadata
    assert region_result.metadata["requires_full_page_image"] is False
    assert "normalization" not in result.manifest.confidence


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
                source_engine="qwen3_vl_8b",
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


def test_qwen_semantic_client_uses_only_active_smart_semantic_url(
    monkeypatch,
) -> None:
    captured: list[tuple[str, str]] = []

    class RecordingClient:
        def __init__(self, *, profile: Any, http_client_base_url: str) -> None:
            captured.append((profile.name, http_client_base_url))

    monkeypatch.setattr(qwen_gateway, "QwenVLClient", RecordingClient)
    settings = qwen_gateway.Settings(
        model_qwen_semantic_url="http://model-qwen-semantic:8104",
    )

    qwen_gateway.QwenSemanticVisionClient.from_settings(settings)

    assert captured == [
        ("qwen3-vl-8b-fp8-semantic:v1", "http://model-qwen-semantic:8104"),
    ]


def _semantic_payload(page_id) -> dict[str, object]:
    return _semantic_payload_for_pages([page_id])


def _docling_context_from_prompt(prompt: str) -> dict[str, Any]:
    _, context_json = prompt.split("Docling context: ", 1)
    context = json.loads(context_json)
    assert isinstance(context, dict)
    return context


def _semantic_payload_for_pages(page_ids) -> dict[str, object]:
    pages = []
    regions = []
    for index, page_id in enumerate(page_ids, start=1):
        pages.append(
            {
                "page_id": str(page_id),
                "page_number": index,
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
        )
        regions.append(
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
        )
    return {
        "schema_name": "semantic_annotation_model_output",
        "schema_version": "v1",
        "document_type": "invoice",
        "pages": pages,
        "regions": regions,
        "quality_flags": {"needs_human_review": False, "visual_degradation": False},
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
    return _source_with_many_page_images(2)


def _source_with_blank_second_page() -> ExtractionSourceDocument:
    source = _source_with_two_page_images()
    blank_content = b"blank-page"
    return replace(
        source,
        pages=[
            source.pages[0],
            ParsedPageText(
                page_id=source.pages[1].page_id,
                page_number=2,
                text="",
                image_bytes=blank_content,
                image_mime_type="image/png",
                image_sha256=hashlib.sha256(blank_content).hexdigest(),
            ),
        ],
    )


def _source_with_many_page_images(page_count: int) -> ExtractionSourceDocument:
    first_page = uuid4()
    pages = []
    for index in range(page_count):
        content = f"page-{index + 1}".encode()
        text = (
            "Invoice cover"
            if index == 0
            else "Invoice total $42"
            if index == 1
            else f"Invoice continuation page {index + 1}"
        )
        pages.append(
            ParsedPageText(
                page_id=first_page if index == 0 else uuid4(),
                page_number=index + 1,
                text=text,
                image_bytes=content,
                image_mime_type="image/png",
                image_sha256=hashlib.sha256(content).hexdigest(),
            )
        )
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
        pages=pages,
        elements=[],
        tables=[],
    )
