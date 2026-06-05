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
_RETAIL_ORDER_TOTAL_TERMS = (
    "total",
    "amount paid",
    "tax",
    "shipping",
    "subtotal",
)
_RETAIL_ORDER_PAYMENT_FIELDS = ("subtotal", "tax", "shipping", "total_amount")
_RECEIPT_PAYMENT_FIELDS = ("subtotal", "tax", "payment_method", "total_amount")
_OBSERVATION_DOCUMENT_TYPES = frozenset(
    {
        "real_estate_title",
        "mortgage_escrow_statement",
        "financial_dispute_form",
    }
)
_GENERIC_DOCUMENT_TYPES = frozenset(
    {
        "document_observation",
        "generic",
        "generic_form",
        "no_extraction_target",
        "unsupported_document",
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
_MEDICAL_EOB_APPEAL_TERMS = (
    "appeal",
    "coverage decision",
    "denial",
    "denied",
    "grievance",
    "medical necessity",
)
_MEDICAL_EOB_DECISION_FIELDS = (
    "appeal_deadline",
    "denial_reason",
    "grievance_rights",
    "request_status",
)
_MEDICAL_EOB_DECISION_PAGE_TERMS = (
    "appeal",
    "clinical guideline",
    "coverage decision",
    "diagnosis and treatment codes",
    "denial",
    "denied",
    "dispute resolution",
    "grievance",
    "medical necessity",
    "rights available to members",
)
_MEDICAL_EOB_MAX_DECISION_REGIONS = 5
_RECEIPT_PAYMENT_SUMMARY_FAMILIES = frozenset(
    {
        "receipt",
        "retail_order",
        "service_record",
    }
)
_SERVICE_RECORD_PAYMENT_TERMS = (
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
_SERVICE_RECORD_LINE_ITEM_TERMS = (
    "labor operation",
    "line total",
    "part number",
    "quantity",
    "service description",
)


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
    regions = [_normalize_region(source, manifest, region) for region in manifest.regions]
    regions = _drop_low_value_regions(regions)
    regions = _drop_unanchored_observation_family_regions(source, manifest, regions)
    regions = _normalize_retail_order_regions(source, manifest, regions)
    regions = _normalize_service_record_regions(source, manifest, regions)
    regions = _drop_unsupported_model_payment_summaries(source, manifest, regions)
    regions = _with_medical_eob_decision_pages(source, manifest, regions)
    regions = _dedupe_page_kvp_regions(regions)
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
    manifest: DocumentSemanticManifest,
    region: SemanticRegionAnnotation,
) -> SemanticRegionAnnotation:
    normalized = _normalize_table_grounding(source, region)
    normalized = _normalize_page_scoped_kvp_grounding(source, normalized)
    normalized = _normalize_medical_eob_generic_region(source, manifest, normalized)
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
    if region.semantic_type == "service_record_line_item_table":
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


def _normalize_medical_eob_generic_region(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    region: SemanticRegionAnnotation,
) -> SemanticRegionAnnotation:
    if region.semantic_type != "generic_form_kvp":
        return region
    if region.granite_task != "kvp":
        return region
    if not _is_medical_eob_source(source, manifest):
        return region
    page_text = _normalized_text(_page_text_for_region(source, region))
    if not any(term in page_text for term in _MEDICAL_EOB_APPEAL_TERMS):
        return region
    metadata = {
        **region.metadata,
        "semantic_planner_normalization": {
            "from": "generic_form_kvp",
            "to": "denial_or_coverage_decision",
            "reason": "medical_eob_appeal_or_denial_anchor",
        },
    }
    expected_fields = tuple(
        dict.fromkeys(sorted((*region.expected_fields, *_MEDICAL_EOB_DECISION_FIELDS)))
    )
    return replace(
        region,
        semantic_type="denial_or_coverage_decision",
        target_schema="medical_eob",
        expected_fields=expected_fields,
        metadata=metadata,
    )


def _with_retail_order_payment_summary(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if not _is_retail_order_source(source, manifest):
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


def _with_receipt_payment_summary(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if not _is_receipt_source(source, manifest):
        return regions
    if any(region.semantic_type == "receipt_payment_summary" for region in regions):
        return regions
    page_id = _receipt_payment_summary_page(source)
    if page_id is None:
        return regions
    return [
        *regions,
        SemanticRegionAnnotation(
            semantic_type="receipt_payment_summary",
            priority="high",
            granite_task="kvp",
            target_schema="receipt",
            expected_fields=_RECEIPT_PAYMENT_FIELDS,
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            review_required=True,
            reason="Docling text anchors indicate a receipt payment summary.",
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
    if not _is_retail_order_source(source, manifest):
        return _with_receipt_payment_summary(source, manifest, regions)

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


def _drop_unsupported_model_payment_summaries(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if _supports_receipt_payment_summary(source, manifest):
        return regions
    return [
        region
        for region in regions
        if not (
            region.semantic_type == "receipt_payment_summary"
            and region.metadata.get("region_source") != DOCLING_STRUCTURAL_REGION_SOURCE
        )
    ]


def _normalize_service_record_regions(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if not _is_service_record_source(source, manifest):
        return regions
    summary_page_id = _service_record_payment_summary_page(source)
    if summary_page_id is None:
        return regions

    normalized: list[SemanticRegionAnnotation] = []
    has_summary = False
    for region in regions:
        if region.semantic_type == "receipt_payment_summary":
            if region.grounding.page_id == summary_page_id:
                normalized.append(region)
                has_summary = True
            continue
        if (
            region.semantic_type == "service_record_line_item_table"
            and region.grounding.page_id == summary_page_id
            and region.grounding.kind != "table"
        ):
            continue
        normalized.append(region)

    if has_summary:
        return normalized
    return [
        *normalized,
        SemanticRegionAnnotation(
            semantic_type="receipt_payment_summary",
            priority="high",
            granite_task="kvp",
            target_schema="receipt",
            expected_fields=_RECEIPT_PAYMENT_FIELDS,
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


def _with_medical_eob_decision_pages(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if not _is_medical_eob_source(source, manifest):
        return regions

    existing_decision_pages = {
        page_number
        for region in regions
        if region.semantic_type == "denial_or_coverage_decision"
        and (page_number := _region_page_number(source, region)) is not None
    }
    line_item_pages = {
        page_number
        for region in regions
        if region.semantic_type == "covered_services_line_item_table"
        and (page_number := _region_page_number(source, region)) is not None
    }
    if len(existing_decision_pages) >= _MEDICAL_EOB_MAX_DECISION_REGIONS:
        return regions

    added: list[SemanticRegionAnnotation] = []
    for page in sorted(source.pages, key=lambda item: item.page_number):
        if len(existing_decision_pages) + len(added) >= _MEDICAL_EOB_MAX_DECISION_REGIONS:
            break
        if page.page_number in existing_decision_pages or page.page_number in line_item_pages:
            continue
        page_text = _normalized_text(page.text)
        if not any(term in page_text for term in _MEDICAL_EOB_DECISION_PAGE_TERMS):
            continue
        added.append(
            SemanticRegionAnnotation(
                semantic_type="denial_or_coverage_decision",
                priority="high",
                granite_task="kvp",
                target_schema="medical_eob",
                expected_fields=_MEDICAL_EOB_DECISION_FIELDS,
                grounding=SemanticGroundingRef(kind="page", page_id=page.page_id),
                review_required=True,
                reason="Docling text anchors indicate a medical EOB decision or appeal page.",
                confidence=0.68,
                metadata={
                    "region_source": DOCLING_STRUCTURAL_REGION_SOURCE,
                    "source_signal": "text",
                    "coverage_role": "supporting",
                    "extraction_scope": "page",
                    "must_extract_reason": "medical_eob_decision_or_appeal_context",
                    "semantic_planner_normalization": {
                        "reason": "medical_eob_docling_decision_page_coverage",
                    },
                },
            )
        )
    if not added:
        return regions
    return [*regions, *added]


def _drop_unanchored_observation_family_regions(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    audit = build_docling_audit(source)
    document_type = _document_type(manifest)
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
        if family in {document_type, source_family}:
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


def _receipt_payment_summary_page(source: ExtractionSourceDocument) -> UUID | None:
    audit = build_docling_audit(source)
    if "receipt" not in audit.suggested_family_hints:
        return None
    for page in source.pages:
        page_text = _normalized_text(page.text)
        if "receipt" in page_text and any(term in page_text for term in _RETAIL_ORDER_TOTAL_TERMS):
            return page.page_id
    return _retail_order_payment_summary_page(source)


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


def _is_retail_order_source(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> bool:
    if _document_type(manifest) == "retail_order":
        return True
    if source.family.strip().lower() == "retail_order":
        return True
    return "retail_order" in build_docling_audit(source).suggested_family_hints


def _is_receipt_source(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> bool:
    document_type = _document_type(manifest)
    source_family = source.family.strip().lower()
    if document_type in _OBSERVATION_DOCUMENT_TYPES or source_family in _OBSERVATION_DOCUMENT_TYPES:
        return False
    if document_type == "receipt" or source_family == "receipt":
        return True
    if document_type in _GENERIC_DOCUMENT_TYPES and source_family in {"", "generic"}:
        return False
    audit = build_docling_audit(source)
    if any(family in audit.suggested_family_hints for family in _OBSERVATION_DOCUMENT_TYPES):
        return False
    return "receipt" in audit.suggested_family_hints


def _supports_receipt_payment_summary(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> bool:
    document_type = _document_type(manifest)
    source_family = source.family.strip().lower()
    if document_type in _RECEIPT_PAYMENT_SUMMARY_FAMILIES:
        return True
    if source_family in _RECEIPT_PAYMENT_SUMMARY_FAMILIES:
        return True
    if document_type in _GENERIC_DOCUMENT_TYPES and source_family in {"", "generic"}:
        return False
    audit = build_docling_audit(source)
    return any(
        family in audit.suggested_family_hints for family in _RECEIPT_PAYMENT_SUMMARY_FAMILIES
    )


def _is_service_record_source(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> bool:
    document_type = _document_type(manifest)
    source_family = source.family.strip().lower()
    if document_type == "service_record" or source_family == "service_record":
        return True
    return "service_record" in build_docling_audit(source).suggested_family_hints


def _service_record_payment_summary_page(source: ExtractionSourceDocument) -> UUID | None:
    best: tuple[int, int, UUID] | None = None
    for page in source.pages:
        text = _normalized_text(page.text)
        payment_score = sum(1 for term in _SERVICE_RECORD_PAYMENT_TERMS if term in text)
        if payment_score < 2:
            continue
        line_item_score = sum(1 for term in _SERVICE_RECORD_LINE_ITEM_TERMS if term in text)
        score = payment_score - line_item_score
        candidate = (-score, page.page_number, page.page_id)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best is not None else None


def _is_medical_eob_source(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> bool:
    document_type = _document_type(manifest)
    source_family = source.family.strip().lower()
    if document_type == "medical_eob" or source_family == "medical_eob":
        return True
    return "medical_eob" in build_docling_audit(source).suggested_family_hints


def _page_text_for_region(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> str:
    page_number = _region_page_number(source, region)
    if page_number is None and region.grounding.page_id is not None:
        page_number = _page_number_for_id(source, region.grounding.page_id)
    if page_number is None:
        return source.full_text
    return " ".join(page.text for page in source.pages if page.page_number == page_number)


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())
