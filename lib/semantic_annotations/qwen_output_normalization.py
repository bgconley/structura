from __future__ import annotations

from jsonschema import Draft202012Validator, ValidationError

from lib.extraction.models import ExtractionSourceDocument
from lib.model_runtime.contracts import VisionGenerateResponse
from lib.model_runtime.http_client import ModelProtocolError
from lib.semantic_annotations.qwen_output_scope import (
    canonical_payload_filtered_to_source as _canonical_payload_filtered_to_source,
)
from lib.semantic_annotations.qwen_output_types import ValidatedModelOutputPayload
from lib.semantic_annotations.qwen_output_values import (
    EXTRACTION_USEFULNESS as _EXTRACTION_USEFULNESS,
)
from lib.semantic_annotations.qwen_output_values import (
    PAGE_ROLES as _PAGE_ROLES,
)
from lib.semantic_annotations.qwen_output_values import (
    PRIORITIES as _PRIORITIES,
)
from lib.semantic_annotations.qwen_output_values import (
    SEMANTIC_TYPES as _SEMANTIC_TYPES,
)
from lib.semantic_annotations.qwen_output_values import (
    append_unique as _append_unique,
)
from lib.semantic_annotations.qwen_output_values import (
    average_confidence as _average_confidence,
)
from lib.semantic_annotations.qwen_output_values import (
    bounded_string_list as _bounded_string_list,
)
from lib.semantic_annotations.qwen_output_values import (
    confidence_or_none as _confidence_or_none,
)
from lib.semantic_annotations.qwen_output_values import (
    document_type_candidates as _document_type_candidates,
)
from lib.semantic_annotations.qwen_output_values import (
    document_type_or_none as _document_type_or_none,
)
from lib.semantic_annotations.qwen_output_values import (
    expected_fields_from_json,
)
from lib.semantic_annotations.qwen_output_values import (
    first_present as _first_present,
)
from lib.semantic_annotations.qwen_output_values import (
    granite_task_or_none as _granite_task_or_none,
)
from lib.semantic_annotations.qwen_output_values import (
    inferred_semantic_type as _inferred_semantic_type,
)
from lib.semantic_annotations.qwen_output_values import (
    merge_reasons as _merge_reasons,
)
from lib.semantic_annotations.qwen_output_values import (
    normalized_choice as _normalized_choice,
)
from lib.semantic_annotations.qwen_output_values import (
    normalized_escalation_reasons as _normalized_escalation_reasons,
)
from lib.semantic_annotations.qwen_output_values import (
    normalized_page_planner_fields as _normalized_page_planner_fields,
)
from lib.semantic_annotations.qwen_output_values import (
    normalized_region_planner_fields as _normalized_region_planner_fields,
)
from lib.semantic_annotations.qwen_output_values import (
    optional_string as _optional_string,
)
from lib.semantic_annotations.qwen_output_values import (
    select_regions_for_contract as _select_regions_for_contract,
)
from lib.semantic_annotations.qwen_output_values import (
    target_schema_or_none as _target_schema_or_none,
)
from lib.semantic_annotations.schema import semantic_annotation_model_output_schema


def validated_model_output_payload(
    response: VisionGenerateResponse,
    *,
    source: ExtractionSourceDocument,
) -> ValidatedModelOutputPayload:
    normalized = _normalized_model_output_payload(dict(response.normalized_json), source=source)
    try:
        Draft202012Validator(semantic_annotation_model_output_schema()).validate(normalized.payload)
    except ValidationError as exc:
        raise ModelProtocolError(
            f"semantic annotation model output failed schema validation: {exc.message}"
        ) from exc
    return normalized


def _normalized_model_output_payload(
    payload: dict[str, object],
    *,
    source: ExtractionSourceDocument,
) -> ValidatedModelOutputPayload:
    pages = payload.get("pages")
    regions = payload.get("regions")
    if (
        payload.get("schema_name") == "semantic_annotation_model_output"
        and isinstance(pages, list)
        and isinstance(regions, list)
    ):
        return _canonical_payload_normalized_for_source(payload, pages=pages, source=source)
    if isinstance(pages, list):
        return _payload_from_page_annotations(
            {"page_annotations": [_page_annotation_from_page_wrapper(page) for page in pages]},
            source=source,
        )
    page_annotations = payload.get("page_annotations")
    if isinstance(page_annotations, list):
        return _payload_from_page_annotations(payload, source=source)
    page = payload.get("page")
    if isinstance(page, dict):
        return _payload_from_page_annotations(
            {"page_annotations": [_page_annotation_from_page_wrapper(page)]},
            source=source,
        )
    return ValidatedModelOutputPayload(payload=payload, normalization={})


def _canonical_payload_normalized_for_source(
    payload: dict[str, object],
    *,
    pages: list[object],
    source: ExtractionSourceDocument,
) -> ValidatedModelOutputPayload:
    if not all(isinstance(page, dict) for page in pages):
        return _canonical_payload_filtered_to_source(payload, source=source)
    merged_pages, normalization = _merge_duplicate_pages_with_summary(
        [page for page in pages if isinstance(page, dict)]
    )
    normalized_payload = dict(payload)
    normalized_payload["pages"] = merged_pages
    filtered = _canonical_payload_filtered_to_source(normalized_payload, source=source)
    normalization = _merged_normalization(normalization, filtered.normalization)
    return ValidatedModelOutputPayload(payload=filtered.payload, normalization=normalization)


def _merged_normalization(*parts: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for part in parts:
        if part:
            merged.update(part)
    return merged


def _page_annotation_from_page_wrapper(page: dict[str, object]) -> dict[str, object]:
    page_id = page.get("page_id") or page.get("pageId")
    default_granite_task = page.get("granite_task") or page.get("graniteTask")
    default_target_schema = page.get("target_schema") or page.get("targetSchema")
    raw_regions = page.get("regions")
    regions = raw_regions if isinstance(raw_regions, list) else []
    return {
        "page_id": page_id,
        "page_role": page.get("page_role") or page.get("pageRole"),
        "document_type_hint": page.get("document_type_hint") or page.get("documentTypeHint"),
        "extraction_usefulness": page.get("extraction_usefulness")
        or page.get("extractionUsefulness"),
        "is_boilerplate": page.get("is_boilerplate") or page.get("isBoilerplate"),
        "ambiguous": page.get("ambiguous"),
        "escalation_required": page.get("escalation_required") or page.get("escalationRequired"),
        "escalation_reasons": page.get("escalation_reasons") or page.get("escalationReasons"),
        "reason": page.get("reason"),
        "confidence": page.get("confidence"),
        "page_family_hints": _first_present(page, "page_family_hints", "pageFamilyHints"),
        "continuation_group": _first_present(page, "continuation_group", "continuationGroup"),
        "docling_table_signal": _first_present(page, "docling_table_signal", "doclingTableSignal"),
        "requires_cross_page_context": _first_present(
            page,
            "requires_cross_page_context",
            "requiresCrossPageContext",
        ),
        "material_region_count_hint": _first_present(
            page,
            "material_region_count_hint",
            "materialRegionCountHint",
        ),
        "regions": [
            _region_with_page_defaults(
                region,
                default_granite_task=default_granite_task,
                default_target_schema=default_target_schema,
            )
            for region in regions
        ],
    }


def _region_with_page_defaults(
    region: object,
    *,
    default_granite_task: object,
    default_target_schema: object,
) -> object:
    if not isinstance(region, dict):
        return region
    enriched = dict(region)
    if "granite_task" not in enriched and "graniteTask" not in enriched:
        enriched["granite_task"] = default_granite_task
    if "target_schema" not in enriched and "targetSchema" not in enriched:
        enriched["target_schema"] = default_target_schema
    return enriched


def _payload_from_page_annotations(
    payload: dict[str, object],
    *,
    source: ExtractionSourceDocument,
) -> ValidatedModelOutputPayload:
    page_by_id = {str(page.page_id): page for page in source.pages}
    pages: list[dict[str, object]] = []
    regions: list[dict[str, object]] = []
    needs_high_quality_pass = False
    page_annotations = payload.get("page_annotations")
    if not isinstance(page_annotations, list):
        return ValidatedModelOutputPayload(payload=payload, normalization={})
    for item in page_annotations:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id") or item.get("pageId") or "")
        page = page_by_id.get(page_id)
        page_grounding_repaired = False
        if page is None:
            if len(source.pages) != 1:
                raise ModelProtocolError(
                    f"semantic page_annotations output referenced unknown page_id: {page_id}"
                )
            page = source.pages[0]
            page_id = str(page.page_id)
            page_grounding_repaired = True
        raw_regions = item.get("regions")
        page_regions = raw_regions if isinstance(raw_regions, list) else []
        page_needs_high_quality = any(
            bool(region.get("needs_high_quality_pass"))
            for region in page_regions
            if isinstance(region, dict)
        )
        normalized_regions = [
            _normalized_alternate_region(region, page_id=page_id) for region in page_regions
        ]
        needs_high_quality_pass = needs_high_quality_pass or page_needs_high_quality
        pages.append(
            _normalized_alternate_page(
                item,
                page_id=page_id,
                page_number=page.page_number,
                source=source,
                page_regions=normalized_regions,
                page_needs_high_quality=page_needs_high_quality,
                page_grounding_repaired=page_grounding_repaired,
            )
        )
        regions.extend(normalized_regions)
    pages, normalization = _merge_duplicate_pages_with_summary(pages)
    regions = _select_regions_for_contract(regions)
    normalized_payload: dict[str, object] = {
        "schema_name": "semantic_annotation_model_output",
        "schema_version": "v1",
        "document_type": _document_type_from_payload_or_source(payload, source),
        "pages": pages,
        "regions": regions,
        "quality_flags": {
            "needs_high_quality_pass": needs_high_quality_pass,
            "visual_degradation": bool(payload.get("visual_degradation", False)),
            "poor_ocr": bool(payload.get("poor_ocr", False)),
            "ambiguous_document_type": False,
            "reason": None,
        },
    }
    document_type_candidates = _document_type_candidates(payload.get("document_type_candidates"))
    if document_type_candidates:
        normalized_payload["document_type_candidates"] = document_type_candidates
    planner_notes = _bounded_string_list(payload.get("planner_notes"), limit=6, max_length=160)
    if planner_notes:
        normalized_payload["planner_notes"] = planner_notes
    return ValidatedModelOutputPayload(
        payload=normalized_payload,
        normalization=normalization,
    )


def _merge_duplicate_pages_with_summary(
    pages: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    order: list[str] = []
    duplicate_count = 0
    duplicate_page_ids: list[str] = []
    for index, page in enumerate(pages):
        page_id = str(page.get("page_id") or "")
        key = page_id or f"__missing_page_id_{index}"
        if key not in merged:
            merged[key] = dict(page)
            order.append(key)
            continue
        duplicate_count += 1
        if page_id and page_id not in duplicate_page_ids:
            duplicate_page_ids.append(page_id)
        merged[key] = _merge_page(merged[key], page)
    normalization: dict[str, object] = {}
    if duplicate_count:
        normalization = {
            "duplicate_page_annotations_collapsed": duplicate_count,
            "duplicate_page_annotation_page_ids": duplicate_page_ids,
            "duplicate_page_annotation_policy": "merge_by_page_id_preserving_docling_coverage",
        }
    return [merged[key] for key in order], normalization


def _merge_page(
    existing: dict[str, object],
    incoming: dict[str, object],
) -> dict[str, object]:
    merged = dict(existing)
    merged["has_structured_targets"] = bool(existing.get("has_structured_targets")) or bool(
        incoming.get("has_structured_targets")
    )
    merged["ambiguous"] = bool(existing.get("ambiguous")) or bool(incoming.get("ambiguous"))
    merged["escalation_required"] = bool(existing.get("escalation_required")) or bool(
        incoming.get("escalation_required")
    )
    merged["escalation_reasons"] = _merge_reasons(
        existing.get("escalation_reasons"),
        incoming.get("escalation_reasons"),
    )
    if existing.get("confidence") is None and incoming.get("confidence") is not None:
        merged["confidence"] = incoming["confidence"]
    if existing.get("reason") is None and incoming.get("reason") is not None:
        merged["reason"] = incoming["reason"]
    for key in (
        "page_family_hints",
        "continuation_group",
        "docling_table_signal",
        "requires_cross_page_context",
        "material_region_count_hint",
    ):
        if key not in merged and key in incoming:
            merged[key] = incoming[key]
    return merged


def _normalized_alternate_page(
    item: dict[str, object],
    *,
    page_id: str,
    page_number: int,
    source: ExtractionSourceDocument,
    page_regions: list[dict[str, object]],
    page_needs_high_quality: bool,
    page_grounding_repaired: bool,
) -> dict[str, object]:
    del source
    has_structured_targets = any(
        region.get("granite_task") not in {None, "ignore"} for region in page_regions
    )
    escalation_reasons = _normalized_escalation_reasons(item.get("escalation_reasons"))
    if page_needs_high_quality:
        escalation_reasons = _append_unique(escalation_reasons, "validation_sensitive")
    if page_grounding_repaired:
        escalation_reasons = _append_unique(escalation_reasons, "missing_docling_grounding")
    confidence = _average_confidence(page_regions)
    page_payload = {
        "page_id": page_id,
        "page_number": page_number,
        "page_role": _normalized_choice(item.get("page_role"), _PAGE_ROLES)
        or ("mixed" if has_structured_targets else "unknown"),
        "document_type_hint": _document_type_or_none(item.get("document_type_hint")),
        "extraction_usefulness": _normalized_choice(
            item.get("extraction_usefulness"),
            _EXTRACTION_USEFULNESS,
        )
        or ("high" if has_structured_targets else "none"),
        "is_boilerplate": bool(item.get("is_boilerplate", False)),
        "has_structured_targets": has_structured_targets,
        "ambiguous": bool(item.get("ambiguous", False)),
        "escalation_required": bool(item.get("escalation_required", False))
        or bool(escalation_reasons),
        "escalation_reasons": escalation_reasons,
        "reason": _optional_string(item.get("reason")),
        "confidence": _confidence_or_none(item.get("confidence")) or confidence,
    }
    page_payload.update(_normalized_page_planner_fields(item))
    return page_payload


def _normalized_alternate_region(
    item: object,
    *,
    page_id: str,
) -> dict[str, object]:
    if not isinstance(item, dict):
        return _ignored_unmatched_region(
            page_id=page_id,
            reason="Model returned a non-object region.",
        )
    if bool(item.get("unmatched_region") or item.get("unmatchedRegion")):
        return _ignored_unmatched_region(
            page_id=page_id,
            reason=_optional_string(item.get("reason")) or "Model returned an unmatched region.",
        )
    granite_task = _granite_task_or_none(item.get("granite_task") or item.get("graniteTask"))
    target_schema = _target_schema_or_none(item.get("target_schema") or item.get("targetSchema"))
    expected_fields = expected_fields_from_json(item.get("expected_fields"))
    confidence = _confidence_or_none(item.get("confidence"))
    region_payload: dict[str, object] = {
        "semantic_type": _normalized_choice(
            item.get("semantic_type") or item.get("semanticType"),
            _SEMANTIC_TYPES,
        )
        or _inferred_semantic_type(
            granite_task=granite_task,
            target_schema=target_schema,
            expected_fields=expected_fields,
        ),
        "priority": _normalized_choice(item.get("priority"), _PRIORITIES)
        or ("high" if granite_task not in {None, "ignore"} else "medium"),
        "granite_task": granite_task,
        "target_schema": target_schema,
        "expected_fields": list(expected_fields),
        "grounding": _grounding_from_alternate_region(item, page_id=page_id),
        "review_required": bool(item.get("review_required", False))
        or bool(item.get("needs_high_quality_pass", False)),
        "reason": _optional_string(item.get("reason")),
        "confidence": confidence,
    }
    region_payload.update(_normalized_region_planner_fields(item))
    return region_payload


def _ignored_unmatched_region(*, page_id: str, reason: str) -> dict[str, object]:
    return {
        "semantic_type": "unmatched_region",
        "priority": "medium",
        "granite_task": "ignore",
        "target_schema": None,
        "expected_fields": [],
        "grounding": {
            "kind": "page",
            "page_id": page_id,
            "element_id": None,
            "table_id": None,
        },
        "review_required": True,
        "reason": reason,
        "confidence": 0.2,
    }


def _grounding_from_alternate_region(
    item: dict[str, object],
    *,
    page_id: str,
) -> dict[str, object]:
    grounding = item.get("grounding")
    if isinstance(grounding, dict):
        return {
            "kind": str(grounding.get("kind") or "unmatched_region"),
            "page_id": str(grounding["page_id"]) if grounding.get("page_id") else page_id,
            "element_id": (str(grounding["element_id"]) if grounding.get("element_id") else None),
            "table_id": str(grounding["table_id"]) if grounding.get("table_id") else None,
        }
    if item.get("table_id"):
        return {
            "kind": "table",
            "page_id": page_id,
            "element_id": None,
            "table_id": str(item["table_id"]),
        }
    if item.get("element_id"):
        return {
            "kind": "element",
            "page_id": page_id,
            "element_id": str(item["element_id"]),
            "table_id": None,
        }
    if item.get("tableId"):
        return {
            "kind": "table",
            "page_id": page_id,
            "element_id": None,
            "table_id": str(item["tableId"]),
        }
    if item.get("elementId"):
        return {
            "kind": "element",
            "page_id": page_id,
            "element_id": str(item["elementId"]),
            "table_id": None,
        }
    return {
        "kind": "page",
        "page_id": page_id,
        "element_id": None,
        "table_id": None,
    }


def _document_type_from_payload_or_source(
    payload: dict[str, object],
    source: ExtractionSourceDocument,
) -> str:
    del source
    return _document_type_or_none(payload.get("document_type")) or "unknown"
