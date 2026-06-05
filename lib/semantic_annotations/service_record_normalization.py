from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.docling_audit import build_docling_audit
from lib.semantic_annotations.docling_targets import DOCLING_STRUCTURAL_REGION_SOURCE
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)

_PAYMENT_TERMS = (
    "amount paid",
    "balance due",
    "card",
    "cash",
    "credit",
    "paid",
    "payment",
    "subtotal",
    "tax",
    "total",
)
_LINE_ITEM_TERMS = (
    "amount",
    "description",
    "labor operation",
    "line total",
    "operation",
    "part number",
    "qty",
    "quantity",
    "service description",
)
_LINE_ITEM_FIELDS = (
    "service_description",
    "labor_operation",
    "part_number",
    "quantity",
    "unit_price",
    "line_total",
)
_MAX_LINE_ITEM_PAGES = 4


def normalize_service_record_regions(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if not _is_service_record_source(source, manifest):
        return regions

    summary_page_id = _payment_summary_page(source)
    line_regions = _line_item_regions(
        source=source,
        model_regions=[
            region for region in regions if region.semantic_type == "service_record_line_item_table"
        ],
    )

    normalized: list[SemanticRegionAnnotation] = list(line_regions)
    summary_region: SemanticRegionAnnotation | None = None
    for region in regions:
        if region.semantic_type == "receipt_payment_summary":
            if summary_page_id is not None and region.grounding.page_id == summary_page_id:
                summary_region = (
                    region if summary_region is None else _merge_regions(summary_region, region)
                )
            continue
        if region.semantic_type == "service_record_line_item_table":
            continue
        normalized.append(region)

    if summary_region is not None:
        return [*normalized, summary_region]
    if summary_page_id is None:
        return normalized
    return [
        *normalized,
        SemanticRegionAnnotation(
            semantic_type="receipt_payment_summary",
            priority="high",
            granite_task="kvp",
            target_schema="receipt",
            expected_fields=("subtotal", "tax", "payment_method", "total_amount"),
            grounding=SemanticGroundingRef(kind="page", page_id=summary_page_id),
            review_required=True,
            reason="Docling text anchors indicate a service-record payment summary.",
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


def _is_service_record_source(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> bool:
    document_type = _document_type(manifest)
    source_family = source.family.strip().lower()
    if document_type == "service_record" or source_family == "service_record":
        return True
    return "service_record" in build_docling_audit(source).suggested_family_hints


def _line_item_regions(
    *,
    source: ExtractionSourceDocument,
    model_regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    expected_fields = _expected_fields(model_regions)
    page_candidates = _line_item_page_candidates(source)
    if not page_candidates:
        return _fallback_line_item_regions(source, model_regions)

    regions: list[SemanticRegionAnnotation] = []
    for index, (page_number, page_id, score) in enumerate(page_candidates[:_MAX_LINE_ITEM_PAGES]):
        regions.append(
            SemanticRegionAnnotation(
                semantic_type="service_record_line_item_table",
                priority="critical",
                granite_task="tables_json",
                target_schema="receipt",
                expected_fields=expected_fields,
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=True,
                reason="Docling text anchors indicate a service-record line-item page.",
                confidence=min(0.86, 0.68 + (score * 0.04)),
                metadata={
                    "region_source": DOCLING_STRUCTURAL_REGION_SOURCE,
                    "source_signal": "text",
                    "coverage_role": "primary" if index == 0 else "continuation",
                    "extraction_scope": "page",
                    "must_extract_reason": "service_record_line_items",
                    "requires_full_page_image": True,
                    "docling_anchor_page_number": page_number,
                    "semantic_planner_normalization": {
                        "reason": "service_record_docling_line_item_page_coverage",
                    },
                },
            )
        )
    return regions


def _expected_fields(model_regions: list[SemanticRegionAnnotation]) -> tuple[str, ...]:
    fields: list[str] = []
    for region in model_regions:
        fields.extend(region.expected_fields)
    if not fields:
        fields.extend(_LINE_ITEM_FIELDS)
    fields.extend(_LINE_ITEM_FIELDS)
    return tuple(dict.fromkeys(fields))


def _line_item_page_candidates(source: ExtractionSourceDocument) -> list[tuple[int, UUID, int]]:
    tables_by_page_text: defaultdict[int, list[str]] = defaultdict(list)
    for table in source.tables:
        table_text = " ".join(
            part
            for part in (
                table.table_markdown or "",
                _render_table_json_for_text(table.table_json),
            )
            if part
        )
        if table_text:
            tables_by_page_text[table.page_number].append(table_text)

    candidates: list[tuple[int, UUID, int]] = []
    for page in source.pages:
        text = _normalized_text(
            " ".join([page.text, *tables_by_page_text.get(page.page_number, [])])
        )
        score = sum(1 for term in _LINE_ITEM_TERMS if term in text)
        if score < 2:
            continue
        candidates.append((page.page_number, page.page_id, score))
    return sorted(candidates, key=lambda item: item[0])


def _fallback_line_item_regions(
    source: ExtractionSourceDocument,
    model_regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    best_by_page: dict[int, SemanticRegionAnnotation] = {}
    for region in model_regions:
        page_number = _region_page_number(source, region)
        if page_number is None:
            continue
        existing = best_by_page.get(page_number)
        if existing is None or _region_preference_key(region) < _region_preference_key(existing):
            best_by_page[page_number] = region

    normalized: list[SemanticRegionAnnotation] = []
    for page_number in sorted(best_by_page):
        region = best_by_page[page_number]
        page_id = _page_id_for_page_number(source, page_number) or region.grounding.page_id
        if page_id is None:
            normalized.append(region)
            continue
        metadata = {
            **region.metadata,
            "semantic_planner_normalization": {
                "reason": "service_record_model_line_item_page_dedupe",
            },
        }
        normalized.append(
            replace(
                region,
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=True,
                metadata=metadata,
            )
        )
    return normalized[:_MAX_LINE_ITEM_PAGES]


def _payment_summary_page(source: ExtractionSourceDocument) -> UUID | None:
    best: tuple[int, int, UUID] | None = None
    for page in source.pages:
        text = _normalized_text(page.text)
        payment_score = sum(1 for term in _PAYMENT_TERMS if term in text)
        if payment_score < 2:
            continue
        line_item_score = sum(1 for term in _LINE_ITEM_TERMS if term in text)
        score = payment_score - line_item_score
        candidate = (-score, page.page_number, page.page_id)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best is not None else None


def _merge_regions(
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
    priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return (
        priority_rank.get(region.priority, 4),
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


def _page_number_for_id(source: ExtractionSourceDocument, page_id: UUID) -> int | None:
    for page in source.pages:
        if page.page_id == page_id:
            return page.page_number
    return None


def _page_number_for_table(source: ExtractionSourceDocument, table_id: UUID) -> int | None:
    for table in source.tables:
        if table.table_id == table_id:
            return table.page_number
    return None


def _page_id_for_page_number(source: ExtractionSourceDocument, page_number: int) -> UUID | None:
    for page in source.pages:
        if page.page_number == page_number:
            return page.page_id
    return None


def _document_type(manifest: DocumentSemanticManifest) -> str | None:
    value = manifest.manifest.get("document_type")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _render_table_json_for_text(value: dict[str, Any]) -> str:
    return str(value) if value else ""
