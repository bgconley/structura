from __future__ import annotations

from dataclasses import replace
from typing import Protocol
from uuid import UUID

from jsonschema import Draft202012Validator, ValidationError

from lib.config.settings import Settings, get_settings
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
from lib.semantic_annotations.manifest_merge import (
    merge_partial_manifests,
    page_manifest_json,
    region_manifest_json,
)
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
from lib.semantic_annotations.prompting import (
    HIGH_QUALITY_PROMPT_VERSION,
    RESCUE_PROMPT_VERSION,
    SMART_PROMPT_VERSION,
    build_semantic_planner_prompt,
)
from lib.semantic_annotations.qwen_output_normalization import (
    expected_fields_from_json,
    validated_model_output_payload,
)
from lib.semantic_annotations.schema import (
    semantic_annotation_manifest_schema,
    semantic_annotation_model_output_schema,
)
from lib.semantic_annotations.target_schema_policy import (
    preferred_target_schema,
    target_schema_from_document_hint,
)
from lib.storage import ObjectStorage

MAX_SEMANTIC_MODEL_ATTEMPTS = 2
SMART_SEMANTIC_MAX_OUTPUT_TOKENS = 6144
PAGE_PLANNER_METADATA_FIELDS = (
    "page_family_hints",
    "continuation_group",
    "docling_table_signal",
    "requires_cross_page_context",
    "material_region_count_hint",
)
REGION_PLANNER_METADATA_FIELDS = (
    "importance",
    "source_signal",
    "coverage_role",
    "extraction_scope",
    "requires_full_page_image",
    "continuation_group",
    "must_extract_reason",
    "negative_routing_reason",
    "min_expected_items",
    "visual_bbox_hint",
)


class SemanticVisionClientProtocol(Protocol):
    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse: ...


class QwenSemanticVisionClient:
    def __init__(
        self,
        *,
        smart: SemanticVisionClientProtocol,
        high_quality: SemanticVisionClientProtocol | None = None,
    ) -> None:
        self._clients = {QWEN_SEMANTIC_PROFILE: smart}
        if high_quality is not None:
            self._clients[QWEN_SEMANTIC_HQ_PROFILE] = high_quality

    @classmethod
    def from_settings(cls, settings: Settings) -> QwenSemanticVisionClient:
        return cls(
            smart=QwenVLClient(
                profile=get_model_profile(QWEN_SEMANTIC_PROFILE),
                http_client_base_url=str(settings.model_qwen_semantic_url),
            ),
            high_quality=(
                QwenVLClient(
                    profile=get_model_profile(QWEN_SEMANTIC_HQ_PROFILE),
                    http_client_base_url=str(settings.model_qwen_hq_url),
                )
                if settings.qwen8_enabled
                else None
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
        max_images = _max_image_inputs_for_profile(profile_name)
        if len(source.pages) <= max_images:
            manifest = self._generate_manifest_for_source(
                source,
                quality_mode=quality_mode,
                profile_name=profile_name,
                prompt_version=prompt_version,
            )
        else:
            manifest = self._annotate_in_page_windows(
                source,
                quality_mode=quality_mode,
                profile_name=profile_name,
                prompt_version=prompt_version,
                max_images=max_images,
            )
        self._validate_manifest_for_source(manifest, source)
        return SemanticAnnotationResult(manifest=manifest)

    def _annotate_in_page_windows(
        self,
        source: ExtractionSourceDocument,
        *,
        quality_mode: str,
        profile_name: str,
        prompt_version: str,
        max_images: int,
    ) -> DocumentSemanticManifest:
        partials: list[DocumentSemanticManifest] = []
        for index in range(0, len(source.pages), max_images):
            chunk_source = _source_for_pages(source, source.pages[index : index + max_images])
            partials.append(
                self._generate_manifest_for_source(
                    chunk_source,
                    quality_mode=quality_mode,
                    profile_name=profile_name,
                    prompt_version=prompt_version,
                    context_source=source,
                    focus_page_numbers={page.page_number for page in chunk_source.pages},
                )
            )
        if not partials:
            raise ModelProtocolError("Semantic annotation requires page image assets.")
        return merge_partial_manifests(
            source,
            partials,
            quality_mode=quality_mode,
            profile_name=profile_name,
            prompt_version=prompt_version,
        )

    def _generate_manifest_for_source(
        self,
        source: ExtractionSourceDocument,
        *,
        quality_mode: str,
        profile_name: str,
        prompt_version: str,
        context_source: ExtractionSourceDocument | None = None,
        focus_page_numbers: set[int] | None = None,
    ) -> DocumentSemanticManifest:
        last_error: Exception | None = None
        for attempt in range(MAX_SEMANTIC_MODEL_ATTEMPTS):
            try:
                response = self._generate_for_source(
                    source,
                    profile_name=profile_name,
                    prompt_version=prompt_version,
                    context_source=context_source,
                    focus_page_numbers=focus_page_numbers,
                )
                manifest = _manifest_from_response(
                    source,
                    quality_mode=quality_mode,
                    response=response,
                )
                self._validate_manifest_for_source(manifest, source)
                return manifest
            except (ModelProtocolError, SemanticAnnotationValidationError) as exc:
                last_error = exc
                if attempt + 1 >= MAX_SEMANTIC_MODEL_ATTEMPTS or not _is_retryable_error(exc):
                    break
        if last_error is None:
            raise ModelProtocolError("Semantic annotation model failed without error details.")
        if isinstance(last_error, SemanticAnnotationValidationError):
            raise ModelProtocolError(
                f"Invalid semantic annotation output: {last_error}"
            ) from last_error
        raise last_error

    def _generate_for_source(
        self,
        source: ExtractionSourceDocument,
        *,
        profile_name: str,
        prompt_version: str,
        context_source: ExtractionSourceDocument | None = None,
        focus_page_numbers: set[int] | None = None,
    ) -> VisionGenerateResponse:
        return self.client.generate(
            VisionGenerateRequest(
                profile_name=profile_name,
                prompt_version=prompt_version,
                prompt=_prompt(context_source or source, focus_page_numbers=focus_page_numbers),
                image_inputs=_image_inputs(source, storage=self.storage),
                response_schema_name="semantic_annotation_model_output",
                response_json_schema=_response_json_schema_for_profile(profile_name),
                max_output_tokens=_max_output_tokens_for_profile(profile_name),
                temperature=0.0,
                timeout_seconds=_timeout_seconds_for_profile(profile_name),
            )
        )

    def _validate_manifest_for_source(
        self,
        manifest: DocumentSemanticManifest,
        source: ExtractionSourceDocument,
    ) -> None:
        validate_manifest(
            manifest,
            valid_page_ids={page.page_id for page in source.pages},
            valid_element_ids={element.element_id for element in source.elements},
            valid_table_ids={table.table_id for table in source.tables},
        )


def _profile_for_mode(quality_mode: str) -> str:
    if quality_mode in {"high_quality", "rescue"}:
        return QWEN_SEMANTIC_HQ_PROFILE
    return QWEN_SEMANTIC_PROFILE


def _prompt_version_for_mode(quality_mode: str) -> str:
    if quality_mode == "high_quality":
        return HIGH_QUALITY_PROMPT_VERSION
    if quality_mode == "rescue":
        return RESCUE_PROMPT_VERSION
    return SMART_PROMPT_VERSION


def _max_image_inputs_for_profile(profile_name: str) -> int:
    return get_model_profile(profile_name).max_images_per_request or 1


def _response_json_schema_for_profile(profile_name: str) -> dict[str, object] | None:
    if profile_name == QWEN_SEMANTIC_PROFILE:
        return semantic_annotation_model_output_schema()
    return None


def _max_output_tokens_for_profile(profile_name: str) -> int:
    if profile_name == QWEN_SEMANTIC_PROFILE:
        return SMART_SEMANTIC_MAX_OUTPUT_TOKENS
    return 4096


def _timeout_seconds_for_profile(profile_name: str) -> int:
    settings = get_settings()
    if profile_name == QWEN_SEMANTIC_HQ_PROFILE:
        return settings.model_qwen_hq_timeout_seconds
    if profile_name == QWEN_SEMANTIC_PROFILE:
        return settings.model_qwen_semantic_timeout_seconds
    return settings.model_http_timeout_seconds


def _source_for_pages(
    source: ExtractionSourceDocument,
    pages: list,
) -> ExtractionSourceDocument:
    page_numbers = {page.page_number for page in pages}
    return ExtractionSourceDocument(
        document_id=source.document_id,
        household_id=source.household_id,
        title=source.title,
        original_filename=source.original_filename,
        mime_type=source.mime_type,
        family=source.family,
        subtype=source.subtype,
        sensitivity=source.sensitivity,
        document_date=source.document_date,
        counterparty_display=source.counterparty_display,
        primary_folder_id=source.primary_folder_id,
        metadata=source.metadata,
        pages=list(pages),
        elements=[element for element in source.elements if element.page_number in page_numbers],
        tables=[table for table in source.tables if table.page_number in page_numbers],
    )


def _prompt(
    source: ExtractionSourceDocument,
    *,
    focus_page_numbers: set[int] | None = None,
) -> str:
    return build_semantic_planner_prompt(source, focus_page_numbers=focus_page_numbers)


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
    model_output = validated_model_output_payload(response, source=source)
    normalized = _canonical_payload_from_model_output(
        response=response,
        model_output=model_output.payload,
    )
    pages_raw = normalized.get("pages")
    regions_raw = normalized.get("regions")
    if not isinstance(pages_raw, list) or not isinstance(regions_raw, list):
        raise ModelProtocolError("Semantic annotation output must include pages and regions.")
    pages = [_page_from_json(item) for item in pages_raw]
    pages = _attach_page_normalization_metadata(pages, model_output.normalization)
    document_type_hint = _document_type_hint(normalized, pages)
    regions = _repair_region_grounding_for_source(
        [_region_from_json(item) for item in regions_raw],
        source=source,
        document_type_hint=document_type_hint,
    )
    sanitized_payload = dict(normalized)
    sanitized_payload["pages"] = [page_manifest_json(page) for page in pages]
    sanitized_payload["regions"] = [region_manifest_json(region) for region in regions]
    confidence = _confidence_from_payload(normalized)
    if model_output.normalization:
        confidence["normalization"] = model_output.normalization
        sanitized_payload["confidence"] = confidence
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
        confidence=confidence,
        manifest=sanitized_payload,
        review_required=any(region.review_required for region in regions),
        input_page_hashes=tuple(response.input_sha256),
    )


def _attach_page_normalization_metadata(
    pages: list[PageSemanticAnnotation],
    normalization: dict[str, object],
) -> list[PageSemanticAnnotation]:
    duplicate_page_ids = normalization.get("duplicate_page_annotation_page_ids")
    if not isinstance(duplicate_page_ids, list):
        return pages
    duplicate_page_id_set = {str(page_id) for page_id in duplicate_page_ids}
    return [
        replace(
            page,
            metadata={
                **page.metadata,
                "normalization": normalization,
            },
        )
        if str(page.page_id) in duplicate_page_id_set
        else page
        for page in pages
    ]


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
        metadata={
            **_metadata_from_fields(item, PAGE_PLANNER_METADATA_FIELDS),
            **_page_escalation_metadata(item),
        },
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
        expected_fields=expected_fields_from_json(item.get("expected_fields")),
        grounding=SemanticGroundingRef(
            kind=str(grounding_raw.get("kind") or "unmatched_region"),  # type: ignore[arg-type]
            page_id=_uuid_or_none(grounding_raw.get("page_id")),
            element_id=_uuid_or_none(grounding_raw.get("element_id")),
            table_id=_uuid_or_none(grounding_raw.get("table_id")),
        ),
        review_required=bool(item.get("review_required", False)),
        reason=str(item["reason"]) if item.get("reason") else None,
        confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
        metadata=_metadata_from_fields(item, REGION_PLANNER_METADATA_FIELDS),
    )


def _metadata_from_fields(
    item: dict[str, object],
    fields: tuple[str, ...],
) -> dict[str, object]:
    return {field: item[field] for field in fields if field in item}


def _page_escalation_metadata(item: dict[str, object]) -> dict[str, object]:
    escalation_reasons = item.get("escalation_reasons")
    if not isinstance(escalation_reasons, list):
        return {}
    return {
        "escalation_reasons": [reason for reason in escalation_reasons if isinstance(reason, str)]
    }


def _repair_region_grounding_for_source(
    regions: list[SemanticRegionAnnotation],
    *,
    source: ExtractionSourceDocument,
    document_type_hint: str | None = None,
) -> list[SemanticRegionAnnotation]:
    valid_page_ids = {page.page_id for page in source.pages}
    valid_element_ids = {element.element_id for element in source.elements}
    valid_table_ids = {table.table_id for table in source.tables}
    repaired = [
        _repair_region_grounding(
            region,
            valid_page_ids=valid_page_ids,
            valid_element_ids=valid_element_ids,
            valid_table_ids=valid_table_ids,
        )
        for region in regions
    ]
    return _deduplicate_region_intents(
        [
            _repair_region_target_schema(
                region,
                source=source,
                document_type_hint=document_type_hint,
            )
            for region in repaired
        ]
    )


def _repair_region_grounding(
    region: SemanticRegionAnnotation,
    *,
    valid_page_ids: set[UUID],
    valid_element_ids: set[UUID],
    valid_table_ids: set[UUID],
) -> SemanticRegionAnnotation:
    grounding = region.grounding
    if grounding.kind == "page" and grounding.page_id in valid_page_ids:
        return replace(
            region,
            grounding=SemanticGroundingRef(kind="page", page_id=grounding.page_id),
        )
    if grounding.kind == "element" and grounding.element_id in valid_element_ids:
        return replace(
            region,
            grounding=SemanticGroundingRef(kind="element", element_id=grounding.element_id),
        )
    if grounding.kind == "table" and grounding.table_id in valid_table_ids:
        return replace(
            region,
            grounding=SemanticGroundingRef(kind="table", table_id=grounding.table_id),
        )
    if grounding.page_id in valid_page_ids:
        return replace(
            region,
            grounding=SemanticGroundingRef(kind="page", page_id=grounding.page_id),
            review_required=True,
            confidence=_low_confidence(region.confidence),
        )
    return replace(
        region,
        semantic_type="unmatched_region",
        granite_task="ignore",
        target_schema=None,
        expected_fields=(),
        grounding=SemanticGroundingRef(kind="unmatched_region"),
        review_required=True,
        confidence=_low_confidence(region.confidence),
    )


def _low_confidence(confidence: float | None) -> float:
    if confidence is None:
        return 0.2
    return min(confidence, 0.2)


def _repair_region_target_schema(
    region: SemanticRegionAnnotation,
    *,
    source: ExtractionSourceDocument,
    document_type_hint: str | None,
) -> SemanticRegionAnnotation:
    if region.granite_task in {None, "ignore"}:
        return region
    target_schema = preferred_target_schema(
        document_family=source.family,
        document_metadata=source.metadata,
        document_type_hint=document_type_hint,
        semantic_type=region.semantic_type,
        model_target_schema=region.target_schema,
    )
    if region.target_schema is not None:
        if target_schema and region.target_schema != target_schema:
            metadata = dict(region.metadata)
            metadata["original_target_schema"] = region.target_schema
            metadata["target_schema_repaired"] = True
            return replace(
                region,
                target_schema=target_schema,
                review_required=True,
                confidence=_low_confidence(region.confidence),
                metadata=metadata,
            )
        return region
    if target_schema:
        return replace(
            region,
            target_schema=target_schema,
            review_required=True,
            confidence=_low_confidence(region.confidence),
        )
    return replace(
        region,
        granite_task="ignore",
        review_required=True,
        confidence=_low_confidence(region.confidence),
    )


def _document_type_hint(
    normalized: dict[str, object],
    pages: list[PageSemanticAnnotation],
) -> str | None:
    document_type = normalized.get("document_type")
    if isinstance(document_type, str) and target_schema_from_document_hint(document_type):
        return document_type
    for page in pages:
        if target_schema_from_document_hint(page.document_type_hint):
            return page.document_type_hint
    return None


def _deduplicate_region_intents(
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    deduplicated: list[SemanticRegionAnnotation] = []
    seen: set[tuple[object, ...]] = set()
    for region in regions:
        key = _region_intent_key(region)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(region)
    return deduplicated


def _region_intent_key(region: SemanticRegionAnnotation) -> tuple[object, ...]:
    grounding = region.grounding
    return (
        region.semantic_type,
        region.granite_task,
        region.target_schema,
        tuple(sorted(region.expected_fields)),
        grounding.kind,
        grounding.page_id,
        grounding.element_id,
        grounding.table_id,
    )


def _uuid_or_none(value: object) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _canonical_payload_from_model_output(
    *,
    response: VisionGenerateResponse,
    model_output: dict[str, object],
) -> dict[str, object]:
    payload = dict(model_output)
    payload["schema_name"] = "semantic_annotation_manifest"
    payload["confidence"] = _confidence_from_response_or_model_output(
        response=response,
        model_output=model_output,
    )
    try:
        Draft202012Validator(semantic_annotation_manifest_schema()).validate(payload)
    except ValidationError as exc:
        raise ModelProtocolError(
            f"semantic annotation canonical payload failed schema validation: {exc.message}"
        ) from exc
    return payload


def _confidence_from_response_or_model_output(
    *,
    response: VisionGenerateResponse,
    model_output: dict[str, object],
) -> dict[str, object]:
    if response.confidence_json:
        return {str(key): value for key, value in response.confidence_json.items()}
    confidences: list[float] = []
    for collection_name in ("pages", "regions"):
        collection = model_output.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            confidence = item.get("confidence")
            if isinstance(confidence, int | float):
                confidences.append(float(confidence))
    if confidences:
        return {"overall": sum(confidences) / len(confidences)}
    return {}


def _confidence_from_payload(payload: dict[str, object]) -> dict[str, object]:
    confidence = payload.get("confidence")
    if not isinstance(confidence, dict):
        return {}
    return {str(key): value for key, value in confidence.items()}


def _is_retryable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        fragment in message
        for fragment in (
            "truncated",
            "not valid json",
            "schema validation",
            "semantic annotation output",
            "invalid semantic annotation output",
        )
    )
