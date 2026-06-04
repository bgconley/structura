from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument, ParsedElementText, ParsedPageText
from lib.extraction.visual_input_geometry import (
    basis_from_bbox,
    basis_from_metadata,
    bbox_to_pixels,
    crop_box,
    expanded_bbox,
    normalize_bbox,
    rotation_policy,
)
from lib.extraction.visual_input_types import (
    MAX_CROP_AREA_RATIO,
    MIN_CROP_SHORT_EDGE,
    BBoxBasis,
    CropQualityReport,
    PixelBBox,
    PlannedImageInput,
    VisualInputAttempt,
    VisualInputDecision,
    VisualInputMode,
    VisualInputPlan,
    VisualInputScope,
)
from lib.model_runtime.contracts import ModelImageInput
from lib.model_runtime.http_client import ModelProtocolError
from lib.semantic_annotations.models import SemanticExtractionTask

_CROP_FIRST_TYPES = {
    "invoice_line_item_table",
    "covered_services_line_item_table",
    "receipt_line_item_table",
    "retail_order_line_item_table",
    "service_record_line_item_table",
    "dispute_transaction_table",
}
_FULL_PAGE_TYPES = {
    "document_observation",
    "seller_information_block",
    "escrow_summary",
    "mortgage_payment_summary",
    "patient_responsibility_summary",
    "payment_summary",
    "receipt_payment_summary",
    "billing_summary",
}
_HEADER_FOOTER_BAND_RATIO = 0.08


@dataclass(frozen=True)
class _PageImage:
    page: ParsedPageText
    content: bytes
    mime_type: str
    sha256: str
    width_px: int | None
    height_px: int | None


@dataclass(frozen=True)
class _BBoxCandidate:
    bbox: list[float]
    basis: BBoxBasis
    scope: VisualInputScope
    confidence: float | None
    source: str


def visual_input_mode_from_env() -> VisualInputMode:
    value = os.getenv("STRUCTURA_GRANITE_VISUAL_INPUT_MODE", "shadow_full_page").strip()
    if value in {"full_page", "shadow_full_page", "planned"}:
        return value  # type: ignore[return-value]
    return "shadow_full_page"


def plan_granite_visual_inputs(
    source: ExtractionSourceDocument,
    *,
    semantic_task: SemanticExtractionTask | None,
    max_images: int,
    page_image_loader: Any,
    mode: VisualInputMode | None = None,
    retry_scope: VisualInputScope | None = None,
) -> VisualInputDecision:
    selected_mode = mode or visual_input_mode_from_env()
    pages = _candidate_pages(source, semantic_task=semantic_task)
    planned: list[PlannedImageInput] = []
    for page in pages:
        page_image = _load_page_image(page, page_image_loader)
        plan, image_input = _plan_for_page(
            source=source,
            page_image=page_image,
            semantic_task=semantic_task,
            mode=selected_mode,
            retry_scope=retry_scope,
        )
        planned.append(PlannedImageInput(image_input=image_input, plan=plan))
        if len(planned) >= max_images:
            break
    if not planned:
        raise ModelProtocolError("Vision extraction requires page image assets.")
    return VisualInputDecision(inputs=tuple(planned))


def visual_input_attempt_json(
    *,
    decision: VisualInputDecision,
    useful: bool | None,
    failure_reason: str | None = None,
) -> dict[str, object]:
    return VisualInputAttempt(
        plan=decision.primary_plan,
        useful=useful,
        failure_reason=failure_reason,
    ).as_json()


def crop_retry_allowed(decision: VisualInputDecision) -> bool:
    plan = decision.primary_plan
    if plan is None:
        return False
    return plan.effective_scope in {"element_crop", "table_crop", "bbox_crop", "expanded_crop"}


def is_useful_granite_output(
    *,
    normalized_json: dict[str, Any],
    semantic_task: SemanticExtractionTask | None,
) -> bool:
    if _contains_echo(normalized_json):
        return False
    if _is_all_null_or_empty(normalized_json):
        return False
    semantic_type = semantic_task.semantic_type if semantic_task else ""
    if semantic_type in _CROP_FIRST_TYPES:
        line_items = normalized_json.get("line_items")
        if isinstance(line_items, list):
            return any(not _is_all_null_or_empty(item) for item in line_items)
        return False
    observations = normalized_json.get("observations")
    if isinstance(observations, list) and semantic_task and semantic_task.expected_fields:
        return any(not _is_all_null_or_empty(item) for item in observations)
    return True


def _plan_for_page(
    *,
    source: ExtractionSourceDocument,
    page_image: _PageImage,
    semantic_task: SemanticExtractionTask | None,
    mode: VisualInputMode,
    retry_scope: VisualInputScope | None,
) -> tuple[VisualInputPlan, ModelImageInput]:
    if retry_scope == "full_page_retry":
        image_input = _model_input(page_image)
        return (
            _full_page_plan(
                mode=mode,
                page_image=page_image,
                scope="full_page_retry",
                fallback_reason="crop_output_not_useful",
                input_sha256=image_input.sha256,
            ),
            image_input,
        )

    candidate = _bbox_candidate(source, page_image.page, semantic_task)
    intended_scope = _intended_scope(semantic_task, candidate)
    fallback_reason = _full_page_reason(source, page_image, semantic_task, candidate)
    if mode == "full_page" or intended_scope == "full_page" or fallback_reason is not None:
        image_input = _model_input(page_image)
        return (
            _full_page_plan(
                mode=mode,
                page_image=page_image,
                scope="full_page",
                intended_scope=intended_scope,
                fallback_reason=fallback_reason,
                candidate=candidate,
                input_sha256=image_input.sha256,
            ),
            image_input,
        )

    crop_plan = _crop_plan(source, page_image, semantic_task, candidate, mode)
    if crop_plan.fallback_reason is not None:
        image_input = _model_input(page_image)
        shadow_or_fallback_plan = _full_page_plan(
            mode=mode,
            page_image=page_image,
            scope="full_page",
            intended_scope=crop_plan.intended_scope,
            fallback_reason=crop_plan.fallback_reason,
            candidate=candidate,
            crop_quality=crop_plan.crop_quality,
            input_sha256=image_input.sha256,
        )
        return shadow_or_fallback_plan, image_input

    if mode == "shadow_full_page":
        image_input = _model_input(page_image)
        shadow_plan = VisualInputPlan(
            mode=mode,
            intended_scope=crop_plan.intended_scope,
            effective_scope="full_page",
            page_id=crop_plan.page_id,
            page_number=crop_plan.page_number,
            source_page_image_sha256=page_image.sha256,
            input_sha256=image_input.sha256,
            bbox=crop_plan.bbox,
            original_bbox=crop_plan.original_bbox,
            expanded_bbox=crop_plan.expanded_bbox,
            bbox_basis=crop_plan.bbox_basis,
            bbox_confidence=crop_plan.bbox_confidence,
            rotation_policy=crop_plan.rotation_policy,
            expansion_policy=crop_plan.expansion_policy,
            fallback_reason="shadow_mode_sends_full_page",
            crop_quality=crop_plan.crop_quality,
            continuation_group=crop_plan.continuation_group,
        )
        return shadow_plan, image_input

    image_input = _crop_model_input(page_image, crop_plan)
    effective_plan = VisualInputPlan(
        mode=mode,
        intended_scope=crop_plan.intended_scope,
        effective_scope=crop_plan.effective_scope,
        page_id=crop_plan.page_id,
        page_number=crop_plan.page_number,
        source_page_image_sha256=page_image.sha256,
        input_sha256=image_input.sha256,
        bbox=crop_plan.bbox,
        original_bbox=crop_plan.original_bbox,
        expanded_bbox=crop_plan.expanded_bbox,
        bbox_basis=crop_plan.bbox_basis,
        bbox_confidence=crop_plan.bbox_confidence,
        rotation_policy=crop_plan.rotation_policy,
        expansion_policy=crop_plan.expansion_policy,
        crop_quality=crop_plan.crop_quality,
        continuation_group=crop_plan.continuation_group,
    )
    return effective_plan, image_input


def _crop_plan(
    source: ExtractionSourceDocument,
    page_image: _PageImage,
    semantic_task: SemanticExtractionTask | None,
    candidate: _BBoxCandidate | None,
    mode: VisualInputMode,
) -> VisualInputPlan:
    if candidate is None:
        return _full_page_plan(
            mode=mode,
            page_image=page_image,
            fallback_reason="no_trustworthy_bbox",
        )
    if page_image.width_px is None or page_image.height_px is None:
        return _full_page_plan(
            mode=mode,
            page_image=page_image,
            intended_scope=candidate.scope,
            fallback_reason="image_dimensions_unavailable",
            candidate=candidate,
        )
    page = page_image.page
    selected_rotation_policy = rotation_policy(page.rotation_degrees)
    if selected_rotation_policy != "upright":
        return _full_page_plan(
            mode=mode,
            page_image=page_image,
            intended_scope=candidate.scope,
            fallback_reason="rotation_unresolved",
            candidate=candidate,
        )
    normalized = bbox_to_pixels(
        candidate.bbox,
        candidate.basis,
        page_width_px=page_image.width_px,
        page_height_px=page_image.height_px,
        page_width_points=page.width_points,
        page_height_points=page.height_points,
    )
    if normalized is None:
        return _full_page_plan(
            mode=mode,
            page_image=page_image,
            intended_scope=candidate.scope,
            fallback_reason="bbox_basis_unusable",
            candidate=candidate,
        )
    expanded, expansion_policy = expanded_bbox(
        normalized,
        page_width_px=page_image.width_px,
        page_height_px=page_image.height_px,
        semantic_type=semantic_task.semantic_type if semantic_task else "",
        granite_task=semantic_task.granite_task if semantic_task else None,
        scope=candidate.scope,
        crop_first_types=_CROP_FIRST_TYPES,
    )
    quality = _crop_quality(
        page_image=page_image,
        bbox=expanded,
        semantic_task=semantic_task,
    )
    if not quality.passed:
        return _full_page_plan(
            mode=mode,
            page_image=page_image,
            intended_scope=candidate.scope,
            fallback_reason=quality.failure_reason,
            candidate=candidate,
            crop_quality=quality,
        )
    scope: VisualInputScope = "expanded_crop" if expansion_policy else candidate.scope
    return VisualInputPlan(
        mode=mode,
        intended_scope=candidate.scope,
        effective_scope=scope,
        page_id=page.page_id,
        page_number=page.page_number,
        source_page_image_sha256=page_image.sha256,
        input_sha256=None,
        bbox=expanded,
        original_bbox=candidate.bbox,
        expanded_bbox=expanded if expansion_policy else None,
        bbox_basis=candidate.basis,
        bbox_confidence=candidate.confidence,
        rotation_policy=selected_rotation_policy,
        expansion_policy=expansion_policy,
        crop_quality=quality,
        continuation_group=_continuation_group(semantic_task),
    )


def _full_page_plan(
    *,
    mode: VisualInputMode,
    page_image: _PageImage,
    scope: VisualInputScope = "full_page",
    intended_scope: VisualInputScope = "full_page",
    fallback_reason: str | None = None,
    candidate: _BBoxCandidate | None = None,
    crop_quality: CropQualityReport | None = None,
    input_sha256: str | None = None,
) -> VisualInputPlan:
    return VisualInputPlan(
        mode=mode,
        intended_scope=intended_scope,
        effective_scope=scope,
        page_id=page_image.page.page_id,
        page_number=page_image.page.page_number,
        source_page_image_sha256=page_image.sha256,
        input_sha256=input_sha256,
        original_bbox=candidate.bbox if candidate else None,
        bbox_basis=candidate.basis if candidate else "unknown",
        bbox_confidence=candidate.confidence if candidate else None,
        rotation_policy=rotation_policy(page_image.page.rotation_degrees),
        fallback_reason=fallback_reason,
        crop_quality=crop_quality
        or CropQualityReport(
            page_width_px=page_image.width_px,
            page_height_px=page_image.height_px,
        ),
        continuation_group=_continuation_group(None),
    )


def _candidate_pages(
    source: ExtractionSourceDocument,
    *,
    semantic_task: SemanticExtractionTask | None,
) -> list[ParsedPageText]:
    if semantic_task is None:
        return source.pages
    page_id = semantic_task.grounding.page_id
    if page_id is None and semantic_task.grounding.element_id:
        element = _element_for_id(source, semantic_task.grounding.element_id)
        page_id = _page_id_for_number(source, element.page_number if element else None)
    if page_id is None and semantic_task.grounding.table_id:
        table = next(
            (
                candidate
                for candidate in source.tables
                if candidate.table_id == semantic_task.grounding.table_id
            ),
            None,
        )
        page_id = _page_id_for_number(source, table.page_number if table else None)
    if page_id is None:
        return source.pages
    return [page for page in source.pages if page.page_id == page_id] or source.pages


def _load_page_image(page: ParsedPageText, page_image_loader: Any) -> _PageImage:
    content = page_image_loader(page)
    if not content or not page.image_mime_type:
        raise ModelProtocolError("Vision extraction requires page image assets.")
    sha256 = page.image_sha256 or hashlib.sha256(content).hexdigest()
    width_px, height_px = _image_dimensions(content)
    return _PageImage(
        page=page,
        content=content,
        mime_type=page.image_mime_type,
        sha256=sha256,
        width_px=width_px,
        height_px=height_px,
    )


def _model_input(page_image: _PageImage) -> ModelImageInput:
    return ModelImageInput(
        content=page_image.content,
        mime_type=page_image.mime_type,
        sha256=page_image.sha256,
    )


def _crop_model_input(page_image: _PageImage, plan: VisualInputPlan) -> ModelImageInput:
    if plan.bbox is None:
        return _model_input(page_image)
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency is declared for runtime.
        raise ModelProtocolError("Pillow is required for planned Granite crop inputs.") from exc
    with Image.open(BytesIO(page_image.content)) as image:
        cropped = image.crop(crop_box(plan.bbox))
        output = BytesIO()
        cropped.save(output, format="PNG")
    content = output.getvalue()
    return ModelImageInput(
        content=content,
        mime_type="image/png",
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _image_dimensions(content: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image
    except ImportError:
        return None, None
    try:
        with Image.open(BytesIO(content)) as image:
            width, height = image.size
            return int(width), int(height)
    except Exception:
        return None, None


def _bbox_candidate(
    source: ExtractionSourceDocument,
    page: ParsedPageText,
    semantic_task: SemanticExtractionTask | None,
) -> _BBoxCandidate | None:
    if semantic_task is None:
        return None
    metadata = semantic_task.metadata or {}
    if metadata.get("requires_full_page_image") is True:
        return None
    if semantic_task.grounding.element_id:
        element = _element_for_id(source, semantic_task.grounding.element_id)
        candidate = _candidate_from_element(element, page)
        if candidate is not None:
            return candidate
    if semantic_task.grounding.table_id:
        table = next(
            (
                candidate
                for candidate in source.tables
                if candidate.table_id == semantic_task.grounding.table_id
            ),
            None,
        )
        if table is not None:
            basis = basis_from_metadata(table.metadata) or basis_from_bbox(table.bbox)
            if (
                basis == "unknown"
                and table.bbox is not None
                and page.width_points
                and page.height_points
            ):
                basis = "pdf_points"
            bbox = normalize_bbox(table.bbox)
            if bbox is not None and basis != "unknown":
                return _BBoxCandidate(
                    bbox=bbox,
                    basis=basis,
                    scope="table_crop",
                    confidence=_number(table.metadata.get("bbox_confidence")),
                    source="table_bbox",
                )
            if table.element_id:
                candidate = _candidate_from_element(_element_for_id(source, table.element_id), page)
                if candidate is not None:
                    return _BBoxCandidate(
                        bbox=candidate.bbox,
                        basis=candidate.basis,
                        scope="table_crop",
                        confidence=candidate.confidence,
                        source="table_element_bbox",
                    )
            inferred = _infer_table_bbox_from_elements(source, page, table.table_markdown)
            if inferred is not None:
                return inferred
    hint = metadata.get("visual_bbox_hint")
    basis = basis_from_metadata(metadata) or basis_from_bbox(hint)
    confidence = _number(metadata.get("visual_bbox_confidence"))
    bbox = normalize_bbox(hint)
    if bbox is not None and basis != "unknown" and (confidence is None or confidence >= 0.75):
        return _BBoxCandidate(
            bbox=bbox,
            basis=basis,
            scope="bbox_crop",
            confidence=confidence,
            source="visual_bbox_hint",
        )
    return None


def _candidate_from_element(
    element: ParsedElementText | None,
    page: ParsedPageText,
) -> _BBoxCandidate | None:
    if element is None:
        return None
    bbox = normalize_bbox(element.bbox)
    if bbox is None:
        return None
    basis = basis_from_metadata(element.metadata) or basis_from_bbox(element.bbox)
    if basis == "unknown" and page.width_points and page.height_points:
        basis = "pdf_points"
    if basis == "unknown":
        return None
    return _BBoxCandidate(
        bbox=bbox,
        basis=basis,
        scope="element_crop",
        confidence=_number(element.metadata.get("bbox_confidence")),
        source="element_bbox",
    )


def _infer_table_bbox_from_elements(
    source: ExtractionSourceDocument,
    page: ParsedPageText,
    table_markdown: str | None,
) -> _BBoxCandidate | None:
    if not table_markdown:
        return None
    table_text = table_markdown.lower()
    matched: list[tuple[list[float], BBoxBasis]] = []
    for element in source.elements:
        if element.page_number != page.page_number or not element.text:
            continue
        if element.text.lower() not in table_text:
            continue
        bbox = normalize_bbox(element.bbox)
        basis = basis_from_metadata(element.metadata) or basis_from_bbox(element.bbox)
        if basis == "unknown" and page.width_points and page.height_points:
            basis = "pdf_points"
        if bbox is not None and basis != "unknown":
            matched.append((bbox, basis))
    if len(matched) < 2:
        return None
    basis = matched[0][1]
    if any(item_basis != basis for _, item_basis in matched):
        return None
    return _BBoxCandidate(
        bbox=[
            min(item[0][0] for item in matched),
            min(item[0][1] for item in matched),
            max(item[0][2] for item in matched),
            max(item[0][3] for item in matched),
        ],
        basis=basis,
        scope="table_crop",
        confidence=None,
        source="inferred_table_element_union",
    )


def _intended_scope(
    semantic_task: SemanticExtractionTask | None,
    candidate: _BBoxCandidate | None,
) -> VisualInputScope:
    if semantic_task is None:
        return "full_page"
    if semantic_task.metadata.get("requires_full_page_image") is True:
        return "full_page"
    if semantic_task.semantic_type in _FULL_PAGE_TYPES:
        return "full_page"
    if semantic_task.grounding.kind == "page":
        return "full_page"
    if candidate is not None and semantic_task.semantic_type in _CROP_FIRST_TYPES:
        return candidate.scope
    if candidate is not None and semantic_task.metadata.get("requires_full_page_image") is False:
        return candidate.scope
    return "full_page"


def _full_page_reason(
    source: ExtractionSourceDocument,
    page_image: _PageImage,
    semantic_task: SemanticExtractionTask | None,
    candidate: _BBoxCandidate | None,
) -> str | None:
    del source
    if semantic_task is None:
        return None
    if _continuation_group(semantic_task):
        return "continuation_requires_per_page_visual_plan"
    metadata = semantic_task.metadata or {}
    if metadata.get("requires_full_page_image") is True:
        return "requires_full_page_image"
    if _page_quality_degraded(page_image.page.metadata, metadata):
        return "page_quality_requires_full_page"
    if candidate is None and metadata.get("visual_bbox_hint") is not None:
        return "visual_bbox_hint_untrusted"
    return None


def _crop_quality(
    *,
    page_image: _PageImage,
    bbox: PixelBBox,
    semantic_task: SemanticExtractionTask | None,
) -> CropQualityReport:
    page_width = page_image.width_px
    page_height = page_image.height_px
    if page_width is None or page_height is None:
        return CropQualityReport(passed=False, failure_reason="image_dimensions_unavailable")
    area_ratio = (bbox.width * bbox.height) / max(1, page_width * page_height)
    short_edge = min(bbox.width, bbox.height)
    low_resolution = min(page_width, page_height) < 900
    touches_edge = bbox.x0 <= 0 or bbox.y0 <= 0 or bbox.x1 >= page_width or bbox.y1 >= page_height
    band = int(round(page_height * _HEADER_FOOTER_BAND_RATIO))
    intersects_boilerplate = bbox.y0 < band or bbox.y1 > page_height - band
    density = _content_density(page_image.content, bbox)
    degraded = _page_quality_degraded(
        page_image.page.metadata,
        semantic_task.metadata if semantic_task else {},
    )
    if area_ratio > MAX_CROP_AREA_RATIO:
        failure = "crop_area_too_large"
    elif low_resolution:
        failure = "low_resolution_page_requires_full_page"
    elif short_edge < min(MIN_CROP_SHORT_EDGE, min(page_width, page_height)):
        failure = "crop_too_small"
    elif density is not None and density < 0.006:
        failure = "crop_mostly_blank"
    elif degraded:
        failure = "page_quality_requires_full_page"
    else:
        failure = None
    return CropQualityReport(
        width_px=bbox.width,
        height_px=bbox.height,
        page_width_px=page_width,
        page_height_px=page_height,
        area_ratio=round(area_ratio, 6),
        content_density=density,
        touches_page_edge=touches_edge,
        header_footer_band_intersection=intersects_boilerplate,
        low_resolution=low_resolution,
        degraded_page_quality=degraded,
        passed=failure is None,
        failure_reason=failure,
    )


def _content_density(content: bytes, bbox: PixelBBox) -> float | None:
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return None
    try:
        with Image.open(BytesIO(content)) as image:
            crop = image.crop(crop_box(bbox)).convert("L")
            stat = ImageStat.Stat(crop)
            mean = stat.mean[0]
            extrema = crop.getextrema()
    except Exception:
        return None
    if extrema[0] == extrema[1]:
        return 0.0
    return round(max(0.0, min(1.0, (255.0 - mean) / 255.0)), 6)


def _page_quality_degraded(page_metadata: dict[str, Any], task_metadata: dict[str, Any]) -> bool:
    quality = page_metadata.get("qualitySignals") or page_metadata.get("quality_signals") or {}
    flags = {
        "skewed",
        "degraded",
        "low_text",
        "low_resolution",
        "blurred",
        "handwritten",
        "scan_skewed",
    }
    for key in flags:
        if page_metadata.get(key) is True or task_metadata.get(key) is True:
            return True
        if isinstance(quality, dict) and quality.get(key) is True:
            return True
    return False


def _element_for_id(
    source: ExtractionSourceDocument,
    element_id: UUID | None,
) -> ParsedElementText | None:
    if element_id is None:
        return None
    return next((element for element in source.elements if element.element_id == element_id), None)


def _page_id_for_number(
    source: ExtractionSourceDocument,
    page_number: int | None,
) -> UUID | None:
    if page_number is None:
        return None
    return next((page.page_id for page in source.pages if page.page_number == page_number), None)


def _continuation_group(task: SemanticExtractionTask | None) -> str | None:
    if task is None:
        return None
    group = task.metadata.get("continuation_group") or task.metadata.get("continuationGroup")
    return str(group) if group else None


def _number(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _contains_echo(value: object) -> bool:
    phrases = ("json schema", "return only", "properties", "additionalproperties", "<tables_json>")
    if isinstance(value, str):
        lowered = value.lower()
        return any(phrase in lowered for phrase in phrases)
    if isinstance(value, dict):
        return any(_contains_echo(key) or _contains_echo(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_echo(item) for item in value)
    return False


def _is_all_null_or_empty(value: object) -> bool:
    if value in (None, "", [], {}):
        return True
    if isinstance(value, dict):
        return all(_is_all_null_or_empty(item) for item in value.values())
    if isinstance(value, list):
        return all(_is_all_null_or_empty(item) for item in value)
    return False
