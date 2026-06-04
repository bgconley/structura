from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument
from lib.extraction.visual_input_types import VisualInputPlan
from lib.semantic_annotations.models import SemanticExtractionTask


@dataclass(frozen=True)
class EvidenceContext:
    source_engine: str
    document_id: UUID
    semantic_annotation_id: UUID | None = None
    semantic_region_id: UUID | None = None
    page_id: UUID | None = None
    page_number: int | None = None
    element_id: UUID | None = None
    table_id: UUID | None = None
    visual_input_scope: str | None = None
    visual_input_sha256: str | None = None
    source_page_image_sha256: str | None = None
    bbox: list[int] | None = None
    bbox_basis: str | None = None
    original_bbox: list[float] | None = None
    expanded_bbox: list[int] | None = None
    rotation_policy: str | None = None
    crop_quality: dict[str, Any] | None = None
    visual_input_attempt: int | None = None


def evidence_context_for_task(
    *,
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask | None,
    source_engine: str,
    visual_plan: VisualInputPlan | None = None,
) -> EvidenceContext:
    visual_fields = _visual_fields(visual_plan)
    if semantic_task is None:
        return EvidenceContext(
            source_engine=source_engine,
            document_id=source.document_id,
            **visual_fields,
        )

    page_id = semantic_task.grounding.page_id
    page_number = _page_number_for_page_id(source, page_id)

    if semantic_task.grounding.element_id:
        element = next(
            (
                candidate
                for candidate in source.elements
                if candidate.element_id == semantic_task.grounding.element_id
            ),
            None,
        )
        if element is not None:
            page_number = element.page_number
            page_id = page_id or _page_id_for_page_number(source, page_number)

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
            page_number = table.page_number
            page_id = page_id or _page_id_for_page_number(source, page_number)

    return EvidenceContext(
        source_engine=source_engine,
        document_id=source.document_id,
        semantic_annotation_id=semantic_task.annotation_id,
        semantic_region_id=semantic_task.region_id,
        page_id=page_id,
        page_number=page_number,
        element_id=semantic_task.grounding.element_id,
        table_id=semantic_task.grounding.table_id,
        **visual_fields,
    )


def _visual_fields(visual_plan: VisualInputPlan | None) -> dict[str, Any]:
    if visual_plan is None:
        return {}
    return {
        "visual_input_scope": visual_plan.effective_scope,
        "visual_input_sha256": visual_plan.input_sha256,
        "source_page_image_sha256": visual_plan.source_page_image_sha256,
        "bbox": visual_plan.bbox.as_list() if visual_plan.bbox else None,
        "bbox_basis": visual_plan.bbox_basis,
        "original_bbox": visual_plan.original_bbox,
        "expanded_bbox": visual_plan.expanded_bbox.as_list() if visual_plan.expanded_bbox else None,
        "rotation_policy": visual_plan.rotation_policy,
        "crop_quality": visual_plan.crop_quality.as_json(),
        "visual_input_attempt": visual_plan.selected_attempt_index,
    }


def _page_number_for_page_id(
    source: ExtractionSourceDocument,
    page_id: UUID | None,
) -> int | None:
    if page_id is None:
        return None
    return next((page.page_number for page in source.pages if page.page_id == page_id), None)


def _page_id_for_page_number(
    source: ExtractionSourceDocument,
    page_number: int | None,
) -> UUID | None:
    if page_number is None:
        return None
    return next((page.page_id for page in source.pages if page.page_number == page_number), None)
