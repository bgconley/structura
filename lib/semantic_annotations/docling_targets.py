from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument, ParsedTableText
from lib.semantic_annotations.docling_audit import DoclingAudit, build_docling_audit
from lib.semantic_annotations.manifest_merge import page_manifest_json, region_manifest_json
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)

DOCLING_STRUCTURAL_REGION_SOURCE = "docling_structural"
MAX_DOCLING_STRUCTURAL_TARGETS = 4

_TABLE_FAMILY_PRIORITY = (
    "service_record",
    "retail_order",
    "medical_eob",
    "invoice",
    "receipt",
    "financial_dispute_form",
)
_OBSERVATION_FAMILY_PRIORITY = (
    "real_estate_title",
    "mortgage_escrow_statement",
    "financial_dispute_form",
)
_OBSERVATION_DOMINANT_FAMILIES = frozenset(
    {
        "real_estate_title",
        "mortgage_escrow_statement",
    }
)
_STRONG_TABLE_FAMILIES = frozenset(
    {
        "service_record",
        "retail_order",
        "medical_eob",
        "financial_dispute_form",
    }
)
_TABLE_TARGETS = {
    "service_record": (
        "service_record_line_item_table",
        "receipt",
        (
            "service_description",
            "labor_operation",
            "part_number",
            "quantity",
            "unit_price",
            "line_total",
        ),
    ),
    "retail_order": (
        "retail_order_line_item_table",
        "receipt",
        ("item_description", "sku", "quantity", "unit_price", "line_total"),
    ),
    "medical_eob": (
        "covered_services_line_item_table",
        "medical_eob",
        (
            "service_date",
            "service_description",
            "billed_amount",
            "allowed_amount",
            "patient_responsibility",
        ),
    ),
    "invoice": (
        "invoice_line_item_table",
        "invoice",
        ("description", "quantity", "unit_price", "line_total"),
    ),
    "receipt": (
        "receipt_line_item_table",
        "receipt",
        ("item_description", "quantity", "unit_price", "line_total"),
    ),
    "financial_dispute_form": (
        "dispute_transaction_table",
        "document_observation",
        ("transaction_date", "merchant", "amount", "dispute_reason"),
    ),
    "generic_table": (
        "generic_form_kvp",
        "document_observation",
        ("visible_table_rows", "field_labels", "amounts", "dates"),
    ),
}
_OBSERVATION_TARGETS = {
    "real_estate_title": (
        "seller_information_block",
        ("seller_name", "property_address", "title_company", "closing_reference"),
    ),
    "mortgage_escrow_statement": (
        "escrow_summary",
        ("loan_number", "escrow_shortage", "escrow_surplus", "monthly_payment"),
    ),
    "financial_dispute_form": (
        "dispute_reason_block",
        ("transaction_date", "merchant", "amount", "dispute_reason"),
    ),
}


def augment_result_with_docling_structural_targets(
    source: ExtractionSourceDocument,
    result: SemanticAnnotationResult,
) -> SemanticAnnotationResult:
    augmented_manifest = augment_manifest_with_docling_structural_targets(
        source,
        result.manifest,
    )
    if augmented_manifest is result.manifest:
        return result
    return replace(result, manifest=augmented_manifest)


def augment_manifest_with_docling_structural_targets(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> DocumentSemanticManifest:
    audit = build_docling_audit(source)
    added_regions = _docling_structural_regions(source, manifest, audit)
    if not added_regions:
        return manifest

    regions = [*manifest.regions, *added_regions]
    pages = [
        replace(
            page,
            has_structured_targets=page.has_structured_targets
            or page.page_id in _grounded_page_ids(added_regions, source),
        )
        for page in manifest.pages
    ]
    manifest_payload = dict(manifest.manifest)
    manifest_payload["pages"] = [page_manifest_json(page) for page in pages]
    manifest_payload["regions"] = [region_manifest_json(region) for region in regions]
    manifest_payload["docling_structural_targets"] = {
        "version": "phase8_5_docling_structural_targets_v1",
        "added_region_count": len(added_regions),
        "suggested_family_hints": list(audit.suggested_family_hints),
    }
    confidence = dict(manifest.confidence)
    confidence["docling_structural_targets"] = manifest_payload["docling_structural_targets"]
    return replace(
        manifest,
        pages=pages,
        regions=regions,
        confidence=confidence,
        manifest=manifest_payload,
        review_required=manifest.review_required
        or any(region.review_required for region in added_regions),
    )


def _docling_structural_regions(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    audit: DoclingAudit,
) -> list[SemanticRegionAnnotation]:
    regions: list[SemanticRegionAnnotation] = []
    existing_table_ids = {
        region.grounding.table_id
        for region in manifest.regions
        if region.grounding.table_id is not None
        and region.granite_task is not None
        and region.granite_task != "ignore"
    }
    table_audit_by_id = {summary.table_id: summary for summary in audit.table_summaries}
    table_family = _selected_table_family(audit)
    for table in source.tables:
        if table.table_id in existing_table_ids:
            continue
        table_region = _table_region(
            table,
            audit=audit,
            table_signal=table_audit_by_id.get(table.table_id).table_signal
            if table_audit_by_id.get(table.table_id) is not None
            else "unknown",
            family=table_family,
        )
        if table_region is None:
            continue
        regions.append(table_region)
        if len(regions) >= MAX_DOCLING_STRUCTURAL_TARGETS:
            return regions
    if regions:
        return regions

    existing_semantic_types = {
        region.semantic_type
        for region in manifest.regions
        if region.granite_task is not None and region.granite_task != "ignore"
    }
    dominant_observation_family = _dominant_observation_family(audit)
    observation_families = (
        (dominant_observation_family,)
        if dominant_observation_family is not None
        else _OBSERVATION_FAMILY_PRIORITY
    )
    for family in observation_families:
        if family not in audit.suggested_family_hints:
            continue
        semantic_type, expected_fields = _OBSERVATION_TARGETS[family]
        if semantic_type in existing_semantic_types:
            continue
        page_id = _best_page_for_family(source, family)
        if page_id is None:
            continue
        regions.append(
            SemanticRegionAnnotation(
                semantic_type=semantic_type,
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=expected_fields,
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=True,
                reason=(
                    f"Docling anchors indicate {family} content even though Qwen emitted no "
                    "target."
                ),
                confidence=_confidence_for_family(audit, family),
                metadata=_base_metadata(
                    audit,
                    source="docling_page_anchors",
                    family=family,
                    source_signal="text",
                    coverage_role="primary",
                    extraction_scope="page",
                ),
            )
        )
        if len(regions) >= MAX_DOCLING_STRUCTURAL_TARGETS:
            break
    return regions


def _table_region(
    table: ParsedTableText,
    *,
    audit: DoclingAudit,
    table_signal: str,
    family: str | None,
) -> SemanticRegionAnnotation | None:
    target_family = family
    if target_family is None and table_signal not in {"strong", "weak"}:
        return None
    target = _TABLE_TARGETS[target_family or "generic_table"]
    semantic_type, target_schema, expected_fields = target
    return SemanticRegionAnnotation(
        semantic_type=semantic_type,
        priority="critical" if semantic_type.endswith("line_item_table") else "high",
        granite_task="tables_json",
        target_schema=target_schema,
        expected_fields=expected_fields,
        grounding=SemanticGroundingRef(kind="table", table_id=table.table_id),
        review_required=table_signal in {"weak", "none", "unknown"},
        reason=(
            "Docling table structure produced a Granite extraction target independent of "
            "Qwen semantic region fanout."
        ),
        confidence=0.78 if table_signal == "strong" else 0.62,
        metadata={
            **_base_metadata(
                audit,
                source="docling_table",
                family=target_family or "generic_table",
                source_signal="table",
                coverage_role="primary",
                extraction_scope="table",
            ),
            "docling_table_id": str(table.table_id),
            "docling_table_index": table.table_index,
            "docling_table_page_number": table.page_number,
            "docling_table_signal": table_signal,
            "requires_full_page_image": True,
        },
    )


def _base_metadata(
    audit: DoclingAudit,
    *,
    source: str,
    family: str,
    source_signal: str,
    coverage_role: str,
    extraction_scope: str,
) -> dict[str, Any]:
    return {
        "region_source": DOCLING_STRUCTURAL_REGION_SOURCE,
        "source_signal": source_signal,
        "coverage_role": coverage_role,
        "extraction_scope": extraction_scope,
        "must_extract_reason": "docling_structural_signal",
        "docling_anchor_families": list(audit.suggested_family_hints),
        "docling_structural_target": {
            "source": source,
            "family": family,
            "anchor_counts": audit.anchor_counts,
        },
    }


def _selected_table_family(audit: DoclingAudit) -> str | None:
    hints = set(audit.suggested_family_hints)
    dominant_observation_family = _dominant_observation_family(audit)
    if dominant_observation_family is not None:
        observation_count = audit.anchor_counts.get(dominant_observation_family, 0)
        for family in _TABLE_FAMILY_PRIORITY:
            if family in _STRONG_TABLE_FAMILIES and family in hints:
                if audit.anchor_counts.get(family, 0) >= observation_count + 2:
                    return family
        return None
    for family in _TABLE_FAMILY_PRIORITY:
        if family in hints:
            return family
    return None


def _dominant_observation_family(audit: DoclingAudit) -> str | None:
    candidates = [
        family
        for family in _OBSERVATION_FAMILY_PRIORITY
        if family in _OBSERVATION_DOMINANT_FAMILIES and family in audit.suggested_family_hints
    ]
    if not candidates:
        return None
    priority = {family: index for index, family in enumerate(_OBSERVATION_FAMILY_PRIORITY)}
    return min(
        candidates,
        key=lambda family: (-audit.anchor_counts.get(family, 0), priority[family]),
    )


def _best_page_for_family(source: ExtractionSourceDocument, family: str) -> UUID | None:
    family_terms = _page_anchor_terms(family)
    if family_terms:
        for page in source.pages:
            page_text = " ".join(page.text.lower().replace("&", " & ").split())
            if any(term in page_text for term in family_terms):
                return page.page_id
    return source.pages[0].page_id if source.pages else None


def _page_anchor_terms(family: str) -> tuple[str, ...]:
    if family == "real_estate_title":
        return ("seller", "title company", "closing", "settlement")
    if family == "mortgage_escrow_statement":
        return ("escrow", "mortgage", "shortage", "surplus")
    if family == "financial_dispute_form":
        return ("dispute", "transaction", "unauthorized")
    return ()


def _confidence_for_family(audit: DoclingAudit, family: str) -> float:
    anchor_count = int(audit.anchor_counts.get(family, 0))
    return min(0.92, 0.68 + (anchor_count * 0.05))


def _grounded_page_ids(
    regions: list[SemanticRegionAnnotation],
    source: ExtractionSourceDocument,
) -> set[UUID]:
    table_page_by_id = {table.table_id: table.page_number for table in source.tables}
    page_by_number = {page.page_number: page.page_id for page in source.pages}
    page_ids: set[UUID] = set()
    for region in regions:
        if region.grounding.page_id is not None:
            page_ids.add(region.grounding.page_id)
        elif region.grounding.table_id is not None:
            page_number = table_page_by_id.get(region.grounding.table_id)
            if page_number is not None and page_number in page_by_number:
                page_ids.add(page_by_number[page_number])
    return page_ids
