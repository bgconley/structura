from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument, ParsedTableText
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
_RETAIL_ORDER_TOTAL_TERMS = (
    "total",
    "amount paid",
    "tax",
    "shipping",
    "subtotal",
)
_RETAIL_ORDER_PAYMENT_FIELDS = ("subtotal", "tax", "shipping", "total_amount")


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
    regions = [_normalize_region(source, region) for region in manifest.regions]
    regions = _normalize_retail_order_regions(source, manifest, regions)
    regions = _dedupe_equivalent_regions(regions)
    if regions == manifest.regions:
        return manifest

    manifest_payload = dict(manifest.manifest)
    manifest_payload["pages"] = [page_manifest_json(page) for page in manifest.pages]
    manifest_payload["regions"] = [region_manifest_json(region) for region in regions]

    confidence = dict(manifest.confidence)
    confidence["semantic_planner_normalization"] = {
        "version": "phase8_5-semantic-planner-normalization-v1",
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
    normalized = _normalize_line_item_grounding(source, region)
    if _is_model_planned_line_item(normalized):
        normalized = replace(normalized, review_required=True)
    if _is_model_planned_payment_summary(normalized):
        normalized = replace(normalized, review_required=True)
    return normalized


def _normalize_line_item_grounding(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> SemanticRegionAnnotation:
    if region.semantic_type not in _LINE_ITEM_SEMANTIC_TYPES:
        return region

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


def _with_retail_order_payment_summary(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if _document_type(manifest) != "retail_order":
        return regions
    if any(region.semantic_type == "receipt_payment_summary" for region in regions):
        return regions
    page_id = _retail_order_payment_summary_page(source)
    if page_id is None:
        return regions
    return [
        *regions,
        SemanticRegionAnnotation(
            semantic_type="receipt_payment_summary",
            priority="high",
            granite_task="kvp",
            target_schema="receipt",
            expected_fields=_RETAIL_ORDER_PAYMENT_FIELDS,
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            review_required=True,
            reason="Docling text anchors indicate a retail-order payment summary.",
            confidence=0.68,
            metadata={
                "region_source": DOCLING_STRUCTURAL_REGION_SOURCE,
                "source_signal": "text",
                "coverage_role": "summary",
                "extraction_scope": "page",
                "must_extract_reason": "payment_summary",
            },
        ),
    ]


def _normalize_retail_order_regions(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if _document_type(manifest) != "retail_order":
        return _with_retail_order_payment_summary(source, manifest, regions)

    line_item_ids_to_keep = _retail_order_line_item_ids_to_keep(source, regions)
    normalized: list[SemanticRegionAnnotation] = []
    for region in regions:
        if region.semantic_type == "receipt_payment_summary":
            continue
        if region.semantic_type == "retail_order_line_item_table":
            if id(region) not in line_item_ids_to_keep:
                continue
        normalized.append(region)
    return _with_retail_order_payment_summary(source, manifest, normalized)


def _retail_order_line_item_ids_to_keep(
    source: ExtractionSourceDocument,
    regions: list[SemanticRegionAnnotation],
) -> set[int]:
    best_by_page: dict[int, tuple[tuple[object, ...], SemanticRegionAnnotation]] = {}
    for region in regions:
        if region.semantic_type != "retail_order_line_item_table":
            continue
        page_number = _region_page_number(source, region)
        if page_number is None:
            continue
        key = _retail_order_line_item_key(source, region)
        current = best_by_page.get(page_number)
        if current is None or key < current[0]:
            best_by_page[page_number] = (key, region)
    return {id(region) for _key, region in best_by_page.values()}


def _retail_order_line_item_key(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> tuple[object, ...]:
    grounding = region.grounding
    page_number = _region_page_number(source, region)
    return (
        page_number if page_number is not None else 999_999,
        _table_index_for_id(source, grounding.table_id) if grounding.table_id else 999_999,
        0 if grounding.kind == "table" else 1,
        str(grounding.table_id or ""),
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
    model_line_item_keys = {
        _region_key(region)
        for region in regions
        if _is_model_planned_line_item(region)
        and region.grounding.kind == "table"
        and region.grounding.table_id is not None
    }
    deduped: list[SemanticRegionAnnotation] = []
    for region in regions:
        if (
            region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE
            and region.semantic_type in _LINE_ITEM_SEMANTIC_TYPES
            and _region_key(region) in model_line_item_keys
        ):
            continue
        deduped.append(region)
    return deduped


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


def _retail_order_payment_summary_page(source: ExtractionSourceDocument) -> UUID | None:
    for page in source.pages:
        page_text = _normalized_text(page.text)
        if any(term in page_text for term in _RETAIL_ORDER_TOTAL_TERMS):
            return page.page_id
    return None


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
