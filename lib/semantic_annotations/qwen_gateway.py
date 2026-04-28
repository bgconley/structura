from __future__ import annotations

import json
from typing import Protocol
from uuid import UUID

from lib.config.settings import Settings
from lib.extraction.models import ExtractionSourceDocument
from lib.model_runtime.clients.qwen_vl import QwenVLClient
from lib.model_runtime.contracts import (
    ModelImageInput,
    VisionGenerateRequest,
    VisionGenerateResponse,
)
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import (
    QWEN_SEMANTIC_HQ_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    get_model_profile,
)
from lib.semantic_annotations.docling_context import build_docling_context
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.policy import (
    SemanticAnnotationValidationError,
    validate_manifest,
)
from lib.storage import ObjectStorage


class SemanticVisionClientProtocol(Protocol):
    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse: ...


class QwenSemanticVisionClient:
    def __init__(
        self,
        *,
        smart: SemanticVisionClientProtocol,
        high_quality: SemanticVisionClientProtocol,
    ) -> None:
        self._clients = {
            QWEN_SEMANTIC_PROFILE: smart,
            QWEN_SEMANTIC_HQ_PROFILE: high_quality,
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> QwenSemanticVisionClient:
        return cls(
            smart=QwenVLClient(
                profile=get_model_profile(QWEN_SEMANTIC_PROFILE),
                http_client_base_url=str(settings.model_qwen_url),
            ),
            high_quality=QwenVLClient(
                profile=get_model_profile(QWEN_SEMANTIC_HQ_PROFILE),
                http_client_base_url=str(settings.model_qwen_url),
            ),
        )

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        client = self._clients.get(request.profile_name)
        if client is None:
            raise ModelProtocolError("Unknown Qwen semantic annotation profile.")
        return client.generate(request)


class QwenSemanticAnnotationGateway:
    def __init__(
        self,
        *,
        client: SemanticVisionClientProtocol,
        storage: ObjectStorage | None = None,
    ) -> None:
        self.client = client
        self.storage = storage or ObjectStorage()

    def annotate(
        self,
        source: ExtractionSourceDocument,
        *,
        quality_mode: str,
    ) -> SemanticAnnotationResult:
        profile_name = _profile_for_mode(quality_mode)
        prompt_version = _prompt_version_for_mode(quality_mode)
        response = self.client.generate(
            VisionGenerateRequest(
                profile_name=profile_name,
                prompt_version=prompt_version,
                prompt=_prompt(source),
                image_inputs=_image_inputs(source, storage=self.storage),
                response_schema_name="semantic_annotation_manifest",
                max_output_tokens=4096,
                temperature=0.0,
                timeout_seconds=60,
            )
        )
        manifest = _manifest_from_response(source, quality_mode=quality_mode, response=response)
        try:
            validate_manifest(
                manifest,
                valid_page_ids={page.page_id for page in source.pages},
                valid_element_ids={element.element_id for element in source.elements},
                valid_table_ids={table.table_id for table in source.tables},
            )
        except SemanticAnnotationValidationError as exc:
            raise ModelProtocolError(f"Invalid semantic annotation output: {exc}") from exc
        return SemanticAnnotationResult(manifest=manifest)


def _profile_for_mode(quality_mode: str) -> str:
    if quality_mode in {"high_quality", "rescue"}:
        return QWEN_SEMANTIC_HQ_PROFILE
    return QWEN_SEMANTIC_PROFILE


def _prompt_version_for_mode(quality_mode: str) -> str:
    if quality_mode == "high_quality":
        return "phase8_5-semantic-high-quality-v1"
    if quality_mode == "rescue":
        return "phase8_5-semantic-rescue-v1"
    return "phase8_5-semantic-smart-v1"


def _prompt(source: ExtractionSourceDocument) -> str:
    context = build_docling_context(source)
    return (
        "You are Structura's semantic annotation planner. Docling is the physical "
        "parse authority. Return JSON only with pages[] and regions[] grounded to "
        "Docling page_id, element_id, or table_id whenever possible. Do not extract "
        "canonical facts; identify semantic regions and Granite extraction tasks. "
        "Docling context: "
        f"{json.dumps(context, sort_keys=True)}"
    )


def _image_inputs(
    source: ExtractionSourceDocument,
    *,
    storage: ObjectStorage,
) -> tuple[ModelImageInput, ...]:
    inputs: list[ModelImageInput] = []
    for page in source.pages:
        image_bytes = page.image_bytes
        if image_bytes is None and page.image_asset_uri:
            image_bytes = storage.path_for_uri(page.image_asset_uri).read_bytes()
        if not image_bytes or not page.image_mime_type:
            continue
        inputs.append(
            ModelImageInput(
                content=image_bytes,
                mime_type=page.image_mime_type,
                sha256=page.image_sha256 or "",
            )
        )
    if not inputs:
        raise ModelProtocolError("Semantic annotation requires page image assets.")
    return tuple(inputs)


def _manifest_from_response(
    source: ExtractionSourceDocument,
    *,
    quality_mode: str,
    response: VisionGenerateResponse,
) -> DocumentSemanticManifest:
    normalized = response.normalized_json
    pages_raw = normalized.get("pages")
    regions_raw = normalized.get("regions")
    if not isinstance(pages_raw, list) or not isinstance(regions_raw, list):
        raise ModelProtocolError("Semantic annotation output must include pages and regions.")
    pages = [_page_from_json(item) for item in pages_raw]
    regions = [_region_from_json(item) for item in regions_raw]
    return DocumentSemanticManifest(
        document_id=source.document_id,
        household_id=source.household_id,
        quality_mode=quality_mode,  # type: ignore[arg-type]
        profile_name=response.profile_name,
        source_engine=response.source_engine,
        model_name=response.model_name,
        model_version=response.model_version,
        prompt_version=response.prompt_version,
        pages=pages,
        regions=regions,
        confidence=dict(response.confidence_json),
        manifest=dict(normalized),
        review_required=any(region.review_required for region in regions),
        input_page_hashes=tuple(response.input_sha256),
    )


def _page_from_json(item: object) -> PageSemanticAnnotation:
    if not isinstance(item, dict):
        raise ModelProtocolError("Semantic page annotation must be an object.")
    return PageSemanticAnnotation(
        page_id=UUID(str(item["page_id"])),
        page_number=int(item["page_number"]),
        page_role=str(item.get("page_role") or "unknown"),
        document_type_hint=(
            str(item["document_type_hint"]) if item.get("document_type_hint") else None
        ),
        extraction_usefulness=str(item.get("extraction_usefulness") or "unknown"),
        is_boilerplate=bool(item.get("is_boilerplate", False)),
        has_structured_targets=bool(item.get("has_structured_targets", False)),
        ambiguous=bool(item.get("ambiguous", False)),
        escalation_required=bool(item.get("escalation_required", False)),
        reason=str(item["reason"]) if item.get("reason") else None,
        confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
    )


def _region_from_json(item: object) -> SemanticRegionAnnotation:
    if not isinstance(item, dict):
        raise ModelProtocolError("semantic region annotation must be an object.")
    grounding_raw = item.get("grounding")
    if not isinstance(grounding_raw, dict):
        raise ModelProtocolError("semantic region annotation is missing grounding.")
    return SemanticRegionAnnotation(
        semantic_type=str(item.get("semantic_type") or "unknown"),
        priority=str(item.get("priority") or "medium"),  # type: ignore[arg-type]
        granite_task=str(item["granite_task"]) if item.get("granite_task") else None,
        target_schema=str(item["target_schema"]) if item.get("target_schema") else None,
        expected_fields=tuple(str(value) for value in item.get("expected_fields") or ()),
        grounding=SemanticGroundingRef(
            kind=str(grounding_raw.get("kind") or "unmatched_region"),  # type: ignore[arg-type]
            page_id=_uuid_or_none(grounding_raw.get("page_id")),
            element_id=_uuid_or_none(grounding_raw.get("element_id")),
            table_id=_uuid_or_none(grounding_raw.get("table_id")),
        ),
        review_required=bool(item.get("review_required", False)),
        reason=str(item["reason"]) if item.get("reason") else None,
        confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
    )


def _uuid_or_none(value: object) -> UUID | None:
    if not value:
        return None
    return UUID(str(value))
