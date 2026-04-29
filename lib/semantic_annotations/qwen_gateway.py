from __future__ import annotations

import json
from dataclasses import replace
from typing import Protocol
from uuid import UUID

from jsonschema import Draft202012Validator, ValidationError

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
from lib.semantic_annotations.qwen_output_normalization import (
    expected_fields_from_json,
    validated_model_output_payload,
)
from lib.semantic_annotations.schema import (
    semantic_annotation_manifest_schema,
    semantic_annotation_model_output_schema,
)
from lib.storage import ObjectStorage

MAX_SEMANTIC_MODEL_ATTEMPTS = 2


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
                http_client_base_url=str(settings.model_qwen_semantic_url),
            ),
            high_quality=QwenVLClient(
                profile=get_model_profile(QWEN_SEMANTIC_HQ_PROFILE),
                http_client_base_url=str(settings.model_qwen_hq_url),
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
        if len(source.pages) > max_images:
            manifest = self._annotate_in_page_windows(
                source,
                quality_mode=quality_mode,
                profile_name=profile_name,
                prompt_version=prompt_version,
                max_images=max_images,
            )
        else:
            manifest = self._generate_manifest_for_source(
                source,
                quality_mode=quality_mode,
                profile_name=profile_name,
                prompt_version=prompt_version,
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
                )
            )
        if not partials:
            raise ModelProtocolError("Semantic annotation requires page image assets.")
        return _merge_partial_manifests(
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
    ) -> DocumentSemanticManifest:
        last_error: Exception | None = None
        for attempt in range(MAX_SEMANTIC_MODEL_ATTEMPTS):
            try:
                response = self._generate_for_source(
                    source,
                    profile_name=profile_name,
                    prompt_version=prompt_version,
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
    ) -> VisionGenerateResponse:
        return self.client.generate(
            VisionGenerateRequest(
                profile_name=profile_name,
                prompt_version=prompt_version,
                prompt=_prompt(source),
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
        return "phase8_5-semantic-high-quality-v1"
    if quality_mode == "rescue":
        return "phase8_5-semantic-rescue-v1"
    return "phase8_5-semantic-smart-v1"


def _max_image_inputs_for_profile(_profile_name: str) -> int:
    return 1


def _response_json_schema_for_profile(profile_name: str) -> dict[str, object] | None:
    if profile_name == QWEN_SEMANTIC_PROFILE:
        return semantic_annotation_model_output_schema()
    return None


def _max_output_tokens_for_profile(profile_name: str) -> int:
    if profile_name == QWEN_SEMANTIC_PROFILE:
        return 3840
    return 4096


def _timeout_seconds_for_profile(profile_name: str) -> int:
    if profile_name == QWEN_SEMANTIC_HQ_PROFILE:
        return 180
    return 60


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


def _merge_partial_manifests(
    source: ExtractionSourceDocument,
    partials: list[DocumentSemanticManifest],
    *,
    quality_mode: str,
    profile_name: str,
    prompt_version: str,
) -> DocumentSemanticManifest:
    pages = [page for partial in partials for page in partial.pages]
    regions = [region for partial in partials for region in partial.regions]
    confidence_parts = [partial.confidence for partial in partials if partial.confidence]
    overall_values = [
        float(confidence["overall"])
        for confidence in confidence_parts
        if isinstance(confidence.get("overall"), int | float)
    ]
    confidence: dict[str, object] = {
        "chunk_count": len(partials),
        "chunks": confidence_parts,
    }
    if overall_values:
        confidence["overall"] = sum(overall_values) / len(overall_values)
    document_type = next(
        (
            partial.manifest.get("document_type")
            for partial in partials
            if partial.manifest.get("document_type")
        ),
        source.family,
    )
    return DocumentSemanticManifest(
        document_id=source.document_id,
        household_id=source.household_id,
        quality_mode=quality_mode,  # type: ignore[arg-type]
        profile_name=profile_name,
        source_engine=partials[0].source_engine,
        model_name=partials[0].model_name,
        model_version=partials[0].model_version,
        prompt_version=prompt_version,
        pages=pages,
        regions=regions,
        confidence=confidence,
        manifest={
            "schema_name": "semantic_annotation_manifest",
            "schema_version": "v1",
            "document_type": document_type,
            "pages": [_page_manifest_json(page) for page in pages],
            "regions": [_region_manifest_json(region) for region in regions],
            "quality_flags": {
                "needs_high_quality_pass": any(
                    bool(partial.manifest.get("quality_flags", {}).get("needs_high_quality_pass"))
                    for partial in partials
                    if isinstance(partial.manifest.get("quality_flags"), dict)
                ),
                "visual_degradation": any(
                    bool(partial.manifest.get("quality_flags", {}).get("visual_degradation"))
                    for partial in partials
                    if isinstance(partial.manifest.get("quality_flags"), dict)
                ),
            },
            "confidence": confidence,
        },
        review_required=any(region.review_required for region in regions),
        input_page_hashes=tuple(
            page_hash for partial in partials for page_hash in partial.input_page_hashes
        ),
    )


def _page_manifest_json(page: PageSemanticAnnotation) -> dict[str, object]:
    return {
        "page_id": str(page.page_id),
        "page_number": page.page_number,
        "page_role": page.page_role,
        "document_type_hint": page.document_type_hint,
        "extraction_usefulness": page.extraction_usefulness,
        "is_boilerplate": page.is_boilerplate,
        "has_structured_targets": page.has_structured_targets,
        "ambiguous": page.ambiguous,
        "escalation_required": page.escalation_required,
        "reason": page.reason,
        "confidence": page.confidence,
    }


def _region_manifest_json(region: SemanticRegionAnnotation) -> dict[str, object]:
    return {
        "semantic_type": region.semantic_type,
        "priority": region.priority,
        "granite_task": region.granite_task,
        "target_schema": region.target_schema,
        "expected_fields": list(region.expected_fields),
        "grounding": {
            "kind": region.grounding.kind,
            "page_id": str(region.grounding.page_id) if region.grounding.page_id else None,
            "element_id": (
                str(region.grounding.element_id) if region.grounding.element_id else None
            ),
            "table_id": str(region.grounding.table_id) if region.grounding.table_id else None,
        },
        "review_required": region.review_required,
        "reason": region.reason,
        "confidence": region.confidence,
    }


def _prompt(source: ExtractionSourceDocument) -> str:
    context = build_docling_context(source)
    return (
        "You are Structura's semantic annotation planner. Return valid JSON only as compact "
        "semantic scout JSON, matching the provided semantic_annotation_model_output JSON "
        "Schema. Docling is the physical parse authority: use Docling page_id, element_id, "
        "and table_id from the context instead of inventing coordinates. This is semantic "
        "planning, not extraction: do not output field values, money amounts, dates, names, or "
        "canonical facts. expected_fields must contain field names only, using snake_case "
        "names such as total_amount or patient_responsibility. Produce exactly one page "
        "annotation for each input page image. Return no more than 6 regions total for "
        "this request, and no more than 8 expected_fields per region. Select only the "
        "highest-value Granite routing targets; do not enumerate every visible field. "
        "Keep each reason to one short sentence and do not repeat equivalent regions. "
        "Do not add top-level confidence; page and region confidence values are sufficient. "
        "Add region annotations only for useful Granite extraction targets or no-op boilerplate. "
        "Use target_schema medical_eob for EOB, insurance, denial, and medical billing "
        "documents; invoice for bills and invoices; receipt for receipts and service "
        "records; otherwise null. Use granite_task kvp for summary/key-value blocks, "
        "tables_json for line-item tables, tables_html or tables_otsl only when table "
        "structure requires it, and ignore for boilerplate. Mark unmatched_region, "
        "review_required=true, and low confidence when a useful target cannot be "
        "grounded to Docling IDs. Set "
        "needs_high_quality_pass for poor OCR, ambiguity, validation-sensitive medical, "
        "legal, tax, or financial documents, or low confidence. "
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
    regions = _repair_region_grounding_for_source(
        [_region_from_json(item) for item in regions_raw],
        source=source,
    )
    sanitized_payload = dict(normalized)
    sanitized_payload["regions"] = [_region_manifest_json(region) for region in regions]
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
    )


def _repair_region_grounding_for_source(
    regions: list[SemanticRegionAnnotation],
    *,
    source: ExtractionSourceDocument,
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
        [_repair_region_target_schema(region, source=source) for region in repaired]
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
) -> SemanticRegionAnnotation:
    if region.granite_task in {None, "ignore"} or region.target_schema is not None:
        return region
    target_schema = _default_target_schema_for_source(source)
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


def _default_target_schema_for_source(source: ExtractionSourceDocument) -> str | None:
    family = source.family.strip().lower()
    if family in {"medical_eob", "insurance_denial", "medical_bill"}:
        return "medical_eob"
    if family == "invoice":
        return "invoice"
    if family in {"receipt", "service_record"}:
        return "receipt"
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
    return UUID(str(value))


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
