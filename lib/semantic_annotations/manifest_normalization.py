from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument, ParsedTableText
from lib.semantic_annotations.docling_audit import build_docling_audit
from lib.semantic_annotations.docling_targets import DOCLING_STRUCTURAL_REGION_SOURCE
from lib.semantic_annotations.manifest_merge import page_manifest_json, region_manifest_json
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)

_LINE_ITEM_SEMANTIC_TYPES = frozenset(
    {
        "covered_services_line_item_table",
        "invoice_line_item_table",
        "receipt_line_item_table",
        "retail_order_line_item_table",
        "service_record_line_item_table",
        "dispute_transaction_table",
    }
)
_OBSERVATION_FAMILY_BY_SEMANTIC_TYPE = {
    "seller_information_block": "real_estate_title",
    "escrow_summary": "mortgage_escrow_statement",
    "mortgage_payment_summary": "mortgage_escrow_statement",
    "dispute_reason_block": "financial_dispute_form",
}
_LOW_VALUE_SEMANTIC_TYPES = frozenset(
    {
        "boilerplate",
        "contact_block",
        "document_header",
        "no_extraction_target",
        "unmatched_region",
        "unsupported_document_region",
    }
)
_PAGE_KVP_DEDUPE_TYPES = frozenset(
    {
        "denial_or_coverage_decision",
        "receipt_payment_summary",
        "escrow_summary",
        "mortgage_payment_summary",
        "dispute_reason_block",
        "seller_information_block",
        "generic_form_kvp",
    }
)
_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def normalize_result_for_planning(
    source: ExtractionSourceDocument,
    result: SemanticAnnotationResult,
) -> SemanticAnnotationResult:
    manifest = normalize_manifest_for_planning(source, result.manifest)
    if manifest is result.manifest:
        return result
    return replace(result, manifest=manifest)


def normalize_manifest_for_planning(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> DocumentSemanticManifest:
    # Structural-only normalization per the generalization spec: grounding
    # repair, low-value filtering, and dedupe. Family-specific semantic-intent
    # repairs (semantic-type rewrites, synthetic regions, model-region
    # replacement) are disallowed; recall comes from the Qwen contract plus the
    # Docling structural-target lane.
    regions = [_normalize_region(source, region) for region in manifest.regions]
    regions = _drop_low_value_regions(regions)
    regions = _drop_unanchored_observation_family_regions(source, regions)
    regions = _dedupe_page_kvp_regions(regions)
    regions = _dedupe_equivalent_regions(regions)
    if regions == manifest.regions:
        return manifest

    manifest_payload = dict(manifest.manifest)
    manifest_payload["pages"] = [page_manifest_json(page) for page in manifest.pages]
    manifest_payload["regions"] = [region_manifest_json(region) for region in regions]

    confidence = dict(manifest.confidence)
    confidence["semantic_planner_normalization"] = {
        "version": "phase8_5-semantic-planner-normalization-v2",
        "region_count": len(regions),
    }
    manifest_payload["confidence"] = confidence
    return replace(
        manifest,
        regions=regions,
        confidence=confidence,
        manifest=manifest_payload,
        review_required=manifest.review_required
        or any(region.review_required for region in regions),
    )


def _normalize_region(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> SemanticRegionAnnotation:
    normalized = _normalize_table_grounding(source, region)
    normalized = _normalize_page_scoped_kvp_grounding(source, normalized)
    if _is_model_planned_line_item(normalized):
        normalized = replace(normalized, review_required=True)
    if _is_model_planned_payment_summary(normalized):
        normalized = replace(normalized, review_required=True)
    return normalized


def _normalize_table_grounding(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> SemanticRegionAnnotation:
    grounding = region.grounding
    if grounding.kind == "table" and grounding.table_id is not None:
        page_id = grounding.page_id or _page_id_for_table(source, grounding.table_id)
        if page_id is None or page_id == grounding.page_id:
            return region
        return replace(
            region,
            grounding=SemanticGroundingRef(
                kind="table",
                page_id=page_id,
                table_id=grounding.table_id,
            ),
        )

    if region.semantic_type not in _LINE_ITEM_SEMANTIC_TYPES:
        return region

    if grounding.kind != "page" or grounding.page_id is None:
        return region
    page_number = _page_number_for_id(source, grounding.page_id)
    if page_number is None:
        return region
    tables_on_page = _tables_by_page(source).get(page_number, [])
    if len(tables_on_page) != 1:
        return region
    table = tables_on_page[0]
    metadata = {
        **region.metadata,
        "docling_table_id": str(table.table_id),
        "semantic_grounding_normalization": {
            "from": "page",
            "to": "table",
            "reason": "single_docling_table_on_page",
        },
    }
    return replace(
        region,
        grounding=SemanticGroundingRef(
            kind="table",
            page_id=grounding.page_id,
            table_id=table.table_id,
        ),
        metadata=metadata,
    )


def _normalize_page_scoped_kvp_grounding(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> SemanticRegionAnnotation:
    if region.semantic_type not in _PAGE_KVP_DEDUPE_TYPES:
        return region
    if region.granite_task != "kvp":
        return region
    grounding = region.grounding
    page_id = grounding.page_id
    if page_id is None and grounding.element_id is not None:
        page_id = _page_id_for_element(source, grounding.element_id)
    if page_id is None and grounding.table_id is not None:
        page_id = _page_id_for_table(source, grounding.table_id)
    if page_id is None:
        return region
    if grounding.kind == "page" and grounding.page_id == page_id:
        return region
    metadata = {
        **region.metadata,
        "semantic_grounding_normalization": {
            "from": grounding.kind,
            "to": "page",
            "reason": "page_scoped_kvp_intent",
        },
    }
    return replace(
        region,
        grounding=SemanticGroundingRef(kind="page", page_id=page_id),
        metadata=metadata,
    )


def _drop_unanchored_observation_family_regions(
    source: ExtractionSourceDocument,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    audit = build_docling_audit(source)
    source_family = source.family.strip().lower()
    filtered: list[SemanticRegionAnnotation] = []
    for region in regions:
        family = _OBSERVATION_FAMILY_BY_SEMANTIC_TYPE.get(region.semantic_type)
        if family is None:
            filtered.append(region)
            continue
        if region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE:
            filtered.append(region)
            continue
        if region.grounding.kind == "table":
            continue
        if family in audit.suggested_family_hints:
            filtered.append(region)
            continue
        if family == source_family:
            filtered.append(region)
            continue
        continue
    return filtered


def _drop_low_value_regions(
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    return [
        region
        for region in regions
        if region.semantic_type not in _LOW_VALUE_SEMANTIC_TYPES
        or region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE
    ]


def _dedupe_page_kvp_regions(
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    grouped: dict[tuple[object, ...], SemanticRegionAnnotation] = {}
    order: list[tuple[object, ...]] = []
    for region in regions:
        key = _page_kvp_region_key(region)
        if key is None:
            passthrough_key = ("passthrough", id(region))
            grouped[passthrough_key] = region
            order.append(passthrough_key)
            continue
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = region
            order.append(key)
            continue
        grouped[key] = _merge_page_kvp_regions(existing, region)
    return [grouped[key] for key in order]


def _page_kvp_region_key(region: SemanticRegionAnnotation) -> tuple[object, ...] | None:
    grounding = region.grounding
    if grounding.kind != "page" or grounding.page_id is None:
        return None
    if region.semantic_type not in _PAGE_KVP_DEDUPE_TYPES:
        return None
    if region.granite_task not in {"kvp", "tables_json", "tables_html", "tables_otsl"}:
        return None
    return (
        region.semantic_type,
        region.granite_task,
        region.target_schema,
        grounding.kind,
        grounding.page_id,
    )


def _merge_page_kvp_regions(
    first: SemanticRegionAnnotation,
    second: SemanticRegionAnnotation,
) -> SemanticRegionAnnotation:
    preferred = min((first, second), key=_region_preference_key)
    merged_fields = tuple(dict.fromkeys(sorted((*first.expected_fields, *second.expected_fields))))
    metadata = {
        **preferred.metadata,
        "semantic_planner_normalization": {
            "reason": "duplicate_page_region_intent",
            "merged_semantic_type": preferred.semantic_type,
        },
    }
    return replace(
        preferred,
        expected_fields=merged_fields,
        review_required=first.review_required or second.review_required,
        confidence=max(
            value for value in (first.confidence, second.confidence, 0.0) if value is not None
        ),
        metadata=metadata,
    )


def _region_preference_key(region: SemanticRegionAnnotation) -> tuple[object, ...]:
    return (
        _PRIORITY_RANK.get(region.priority, 4),
        0 if region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE else 1,
        -(region.confidence or 0.0),
    )


def _region_page_number(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> int | None:
    grounding = region.grounding
    if grounding.page_id is not None:
        return _page_number_for_id(source, grounding.page_id)
    if grounding.table_id is not None:
        return _page_number_for_table(source, grounding.table_id)
    return None


def _is_model_planned_line_item(region: SemanticRegionAnnotation) -> bool:
    return (
        region.semantic_type in _LINE_ITEM_SEMANTIC_TYPES
        and region.metadata.get("region_source") != DOCLING_STRUCTURAL_REGION_SOURCE
    )


def _is_model_planned_payment_summary(region: SemanticRegionAnnotation) -> bool:
    return (
        region.semantic_type == "receipt_payment_summary"
        and region.metadata.get("region_source") != DOCLING_STRUCTURAL_REGION_SOURCE
    )


def _dedupe_equivalent_regions(
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    docling_line_item_by_key = {
        _region_key(region): region
        for region in regions
        if region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE
        and region.semantic_type in _LINE_ITEM_SEMANTIC_TYPES
    }
    model_line_item_keys = {
        _region_key(region)
        for region in regions
        if _is_model_planned_line_item(region)
        and region.grounding.kind == "table"
        and region.grounding.table_id is not None
    }
    model_service_record_line_item_page_ids = {
        region.grounding.page_id
        for region in regions
        if _is_model_planned_line_item(region)
        and region.semantic_type == "service_record_line_item_table"
        and region.grounding.kind == "page"
        and region.grounding.page_id is not None
    }
    deduped: list[SemanticRegionAnnotation] = []
    for region in regions:
        if _is_model_planned_line_item(region):
            docling_region = docling_line_item_by_key.get(_region_key(region))
            if docling_region is not None:
                region = _merge_equivalent_region_intent(region, docling_region)
        if (
            region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE
            and region.semantic_type in _LINE_ITEM_SEMANTIC_TYPES
            and _region_key(region) in model_line_item_keys
        ):
            continue
        if (
            region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE
            and region.semantic_type == "service_record_line_item_table"
            and region.grounding.kind == "table"
            and region.grounding.page_id in model_service_record_line_item_page_ids
        ):
            continue
        deduped.append(region)
    return deduped


def _merge_equivalent_region_intent(
    preferred: SemanticRegionAnnotation,
    suppressed: SemanticRegionAnnotation,
) -> SemanticRegionAnnotation:
    merged_fields = tuple(
        dict.fromkeys(sorted((*preferred.expected_fields, *suppressed.expected_fields)))
    )
    if merged_fields == preferred.expected_fields:
        return preferred
    return replace(
        preferred,
        expected_fields=merged_fields,
        review_required=preferred.review_required or suppressed.review_required,
        metadata={
            **preferred.metadata,
            "semantic_planner_normalization": {
                "reason": "equivalent_docling_region_intent_merged",
                "merged_semantic_type": preferred.semantic_type,
            },
        },
    )


def _region_key(region: SemanticRegionAnnotation) -> tuple[object, ...]:
    grounding = region.grounding
    return (
        region.semantic_type,
        region.granite_task,
        region.target_schema,
        grounding.kind,
        grounding.page_id,
        grounding.element_id,
        grounding.table_id,
    )


def _page_number_for_id(source: ExtractionSourceDocument, page_id: UUID) -> int | None:
    for page in source.pages:
        if page.page_id == page_id:
            return page.page_number
    return None


def _page_id_for_table(source: ExtractionSourceDocument, table_id: UUID) -> UUID | None:
    page_by_number = {page.page_number: page.page_id for page in source.pages}
    for table in source.tables:
        if table.table_id == table_id:
            return page_by_number.get(table.page_number)
    return None


def _page_id_for_element(source: ExtractionSourceDocument, element_id: UUID) -> UUID | None:
    page_by_number = {page.page_number: page.page_id for page in source.pages}
    for element in source.elements:
        if element.element_id == element_id:
            return page_by_number.get(element.page_number)
    return None


def _page_number_for_table(source: ExtractionSourceDocument, table_id: UUID) -> int | None:
    for table in source.tables:
        if table.table_id == table_id:
            return table.page_number
    return None


def _table_index_for_id(source: ExtractionSourceDocument, table_id: UUID | None) -> int | None:
    if table_id is None:
        return None
    for table in source.tables:
        if table.table_id == table_id:
            return table.table_index
    return None


def _tables_by_page(source: ExtractionSourceDocument) -> dict[int, list[ParsedTableText]]:
    grouped: defaultdict[int, list[ParsedTableText]] = defaultdict(list)
    for table in source.tables:
        grouped[table.page_number].append(table)
    return dict(grouped)


def _document_type(manifest: DocumentSemanticManifest) -> str | None:
    value = manifest.manifest.get("document_type")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())
