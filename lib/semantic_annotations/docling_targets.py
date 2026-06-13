from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument, ParsedTableText
from lib.semantic_annotations.docling_audit import (
    DoclingAudit,
    build_docling_audit,
    family_anchor_hits_from_text,
    family_has_suggested_hint,
)
from lib.semantic_annotations.manifest_merge import page_manifest_json, region_manifest_json
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.task_routing import (
    LINE_ITEM_TABLE_SEMANTIC_TYPES,
    TABLE_GRANITE_TASKS,
)

DOCLING_STRUCTURAL_REGION_SOURCE = "docling_structural"
MAX_DOCLING_STRUCTURAL_TARGETS = 8

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
_OBSERVATION_SEMANTIC_TYPES = frozenset(
    semantic_type for semantic_type, _expected_fields in _OBSERVATION_TARGETS.values()
)


@dataclass(frozen=True)
class _PageKvpTarget:
    semantic_type: str
    target_schema: str
    expected_fields: tuple[str, ...]
    terms: tuple[str, ...]
    min_term_hits: int = 1


_PAGE_KVP_TARGETS = {
    "medical_eob": (
        _PageKvpTarget(
            semantic_type="denial_or_coverage_decision",
            target_schema="medical_eob",
            expected_fields=(
                "request_status",
                "denial_reason",
                "appeal_deadline",
            ),
            terms=("denied", "denial", "not medically necessary", "appeal"),
            min_term_hits=1,
        ),
        _PageKvpTarget(
            semantic_type="generic_form_kvp",
            target_schema="document_observation",
            expected_fields=(
                "grievance_deadline",
                "grievance_contact",
                "grievance_contact_phone",
                "grievance_contact_fax",
                "grievance_contact_address",
                "grievance_contact_url",
            ),
            terms=("grievance", "external review", "civil action"),
            min_term_hits=1,
        ),
    ),
    "receipt": (
        _PageKvpTarget(
            semantic_type="receipt_payment_summary",
            target_schema="receipt",
            expected_fields=(
                "payment_method",
                "subtotal",
                "tax",
                "tip",
                "total_amount",
            ),
            terms=("subtotal", "sub total", "tax", "total", "amount paid", "payment"),
            min_term_hits=2,
        ),
    ),
    "service_record": (
        _PageKvpTarget(
            semantic_type="receipt_payment_summary",
            target_schema="receipt",
            expected_fields=(
                "payment_method",
                "subtotal",
                "tax",
                "tip",
                "total_amount",
            ),
            terms=("subtotal", "sub total", "tax", "total", "amount paid", "payment"),
            min_term_hits=2,
        ),
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
    coverage_keys = {
        _structural_coverage_key(region)
        for region in manifest.regions
        if _is_active_structural_target(region)
    }
    table_audit_by_id = {summary.table_id: summary for summary in audit.table_summaries}
    page_id_by_number = {page.page_number: page.page_id for page in source.pages}
    for table in source.tables:
        if len(regions) >= MAX_DOCLING_STRUCTURAL_TARGETS:
            break
        table_summary = table_audit_by_id.get(table.table_id)
        table_family = _selected_table_family_for_table(
            source=source,
            table=table,
            audit=audit,
        )
        table_signal = table_summary.table_signal if table_summary is not None else "unknown"
        table_region = _table_region(
            table,
            audit=audit,
            table_signal=table_signal,
            family=table_family,
            page_id=page_id_by_number.get(table.page_number),
        )
        if table_region is None:
            continue
        coverage_key = _structural_coverage_key(table_region)
        if _is_redundant_weak_table_region(
            table_region,
            table_signal=table_signal,
            coverage_keys=coverage_keys,
        ):
            continue
        if coverage_key in coverage_keys:
            continue
        coverage_keys.add(coverage_key)
        regions.append(table_region)

    if len(regions) >= MAX_DOCLING_STRUCTURAL_TARGETS:
        return _dedupe_docling_regions(regions)[:MAX_DOCLING_STRUCTURAL_TARGETS]

    regions.extend(
        _docling_page_kvp_regions(
            source=source,
            audit=audit,
            coverage_keys=coverage_keys,
            remaining=MAX_DOCLING_STRUCTURAL_TARGETS - len(regions),
        )
    )
    if len(regions) >= MAX_DOCLING_STRUCTURAL_TARGETS:
        return _dedupe_docling_regions(regions)[:MAX_DOCLING_STRUCTURAL_TARGETS]

    regions.extend(
        _docling_observation_regions(
            source=source,
            audit=audit,
            coverage_keys=coverage_keys,
            remaining=MAX_DOCLING_STRUCTURAL_TARGETS - len(regions),
        )
    )
    return _dedupe_docling_regions(regions)[:MAX_DOCLING_STRUCTURAL_TARGETS]


def _docling_page_kvp_regions(
    *,
    source: ExtractionSourceDocument,
    audit: DoclingAudit,
    coverage_keys: set[tuple[object, ...]],
    remaining: int,
) -> list[SemanticRegionAnnotation]:
    regions: list[SemanticRegionAnnotation] = []
    for family in _page_kvp_families(source, audit):
        for target in _PAGE_KVP_TARGETS[family]:
            for page in source.pages:
                if len(regions) >= remaining:
                    return regions
                matched_terms = _matched_page_terms(page.text, target.terms)
                if len(matched_terms) < target.min_term_hits:
                    continue
                region = SemanticRegionAnnotation(
                    semantic_type=target.semantic_type,
                    priority="high",
                    granite_task="kvp",
                    target_schema=target.target_schema,
                    expected_fields=target.expected_fields,
                    grounding=SemanticGroundingRef(kind="page", page_id=page.page_id),
                    review_required=True,
                    reason=(
                        f"Docling page text anchors indicate {family} "
                        f"{target.semantic_type} content."
                    ),
                    confidence=0.76,
                    metadata={
                        **_base_metadata(
                            audit,
                            source="docling_page_kvp",
                            family=family,
                            source_signal="text",
                            coverage_role="primary",
                            extraction_scope="page",
                        ),
                        "matched_page_terms": list(matched_terms),
                    },
                )
                coverage_key = _structural_coverage_key(region)
                if coverage_key in coverage_keys:
                    continue
                coverage_keys.add(coverage_key)
                regions.append(region)
    return regions


def _page_kvp_families(
    source: ExtractionSourceDocument,
    audit: DoclingAudit,
) -> tuple[str, ...]:
    del audit
    source_family = (source.family or "").strip().lower()
    if source_family in _PAGE_KVP_TARGETS:
        return (source_family,)
    return ()


def _matched_page_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    page_text = _normalized_text(text)
    return tuple(term for term in terms if term in page_text)


def _normalized_text(value: str) -> str:
    return " ".join(value.lower().replace("&", " & ").split())


def _docling_observation_regions(
    *,
    source: ExtractionSourceDocument,
    audit: DoclingAudit,
    coverage_keys: set[tuple[object, ...]],
    remaining: int,
) -> list[SemanticRegionAnnotation]:
    regions: list[SemanticRegionAnnotation] = []
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
        page_id = _best_page_for_family(source, family)
        if page_id is None:
            continue
        region = SemanticRegionAnnotation(
            semantic_type=semantic_type,
            priority="high",
            granite_task="kvp",
            target_schema="document_observation",
            expected_fields=expected_fields,
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            review_required=True,
            reason=(
                f"Docling anchors indicate {family} content even though Qwen emitted no target."
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
        coverage_key = _structural_coverage_key(region)
        if coverage_key in coverage_keys:
            continue
        coverage_keys.add(coverage_key)
        regions.append(region)
        if len(regions) >= remaining:
            break
    return regions


def _table_region(
    table: ParsedTableText,
    *,
    audit: DoclingAudit,
    table_signal: str,
    family: str | None,
    page_id: UUID | None,
) -> SemanticRegionAnnotation | None:
    target_family = family
    if target_family is None and table_signal not in {"strong", "weak"}:
        return None
    target = _TABLE_TARGETS[target_family or "generic_table"]
    semantic_type, target_schema, expected_fields = target
    return SemanticRegionAnnotation(
        semantic_type=semantic_type,
        priority="critical" if semantic_type in LINE_ITEM_TABLE_SEMANTIC_TYPES else "high",
        granite_task="tables_json",
        target_schema=target_schema,
        expected_fields=expected_fields,
        grounding=SemanticGroundingRef(kind="table", page_id=page_id, table_id=table.table_id),
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


def _is_redundant_weak_table_region(
    region: SemanticRegionAnnotation,
    *,
    table_signal: str,
    coverage_keys: set[tuple[object, ...]],
) -> bool:
    return table_signal == "weak" and _structural_coverage_key(region) in coverage_keys


def _is_table_grounded_observation_summary(region: SemanticRegionAnnotation) -> bool:
    return region.grounding.kind == "table" and region.semantic_type in _OBSERVATION_SEMANTIC_TYPES


def _is_active_structural_target(region: SemanticRegionAnnotation) -> bool:
    return (
        region.granite_task is not None
        and region.granite_task != "ignore"
        and not _is_table_grounded_observation_summary(region)
    )


def _structural_coverage_key(region: SemanticRegionAnnotation) -> tuple[object, ...]:
    grounding = region.grounding
    return (
        region.semantic_type,
        _coverage_task_key(region.granite_task),
        region.target_schema,
        grounding.kind,
        grounding.page_id,
        grounding.element_id,
        grounding.table_id,
        _expected_field_intent(region.expected_fields),
    )


def _coverage_task_key(granite_task: str | None) -> str | None:
    if granite_task in TABLE_GRANITE_TASKS:
        return "table"
    return granite_task


def _expected_field_intent(expected_fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(expected_fields)))


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


def _selected_table_family_for_table(
    *,
    source: ExtractionSourceDocument,
    table: ParsedTableText,
    audit: DoclingAudit,
) -> str | None:
    local_hits = family_anchor_hits_from_text(_normalized_local_table_text(source, table))
    dominant_observation_family = _dominant_observation_family(audit)
    if dominant_observation_family is not None:
        observation_count = audit.anchor_counts.get(dominant_observation_family, 0)
        for family in _TABLE_FAMILY_PRIORITY:
            if (
                family in _STRONG_TABLE_FAMILIES
                and family_has_suggested_hint(family, local_hits.get(family, ()))
                and len(local_hits.get(family, ())) >= observation_count + 1
            ):
                return family
        return None
    for family in _TABLE_FAMILY_PRIORITY:
        if family_has_suggested_hint(family, local_hits.get(family, ())):
            return family
    return _selected_table_family(audit)


def _normalized_local_table_text(
    source: ExtractionSourceDocument,
    table: ParsedTableText,
) -> str:
    page_text = " ".join(
        page.text for page in source.pages if page.page_number == table.page_number and page.text
    )
    table_text = " ".join(
        part
        for part in (
            table.table_markdown or "",
            _render_table_json_for_anchoring(table.table_json),
        )
        if part
    )
    return f"{page_text}\n{table_text}"


def _render_table_json_for_anchoring(table_json: dict[str, Any]) -> str:
    if not table_json:
        return ""
    try:
        return json.dumps(table_json, sort_keys=True)
    except TypeError:
        return str(table_json)


def _dedupe_docling_regions(
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    deduped: list[SemanticRegionAnnotation] = []
    seen: set[tuple[object, ...]] = set()
    for region in regions:
        key = _structural_coverage_key(region)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(region)
    return deduped


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
