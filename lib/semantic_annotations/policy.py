from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)

ALLOWED_GRANITE_TASKS = {
    "kvp",
    "tables_json",
    "tables_html",
    "tables_otsl",
    "chart2csv",
    "chart2summary",
    "chart2code",
    "ignore",
}

ALLOWED_SEMANTIC_TYPES = {
    "document_header",
    "billing_summary",
    "payment_summary",
    "patient_responsibility_summary",
    "covered_services_line_item_table",
    "invoice_line_item_table",
    "receipt_line_item_table",
    "tax_summary",
    "legal_clause",
    "contact_block",
    "signature_block",
    "chart",
    "figure",
    "boilerplate",
    "unmatched_region",
    "unknown",
}

HIGH_RISK_FAMILIES = {
    "medical_eob",
    "medical_bill",
    "legal",
    "tax",
    "financial",
    "insurance",
}


class SemanticAnnotationValidationError(ValueError):
    pass


def validate_manifest(
    manifest: DocumentSemanticManifest,
    *,
    valid_page_ids: Iterable[UUID],
    valid_element_ids: Iterable[UUID],
    valid_table_ids: Iterable[UUID],
) -> None:
    page_ids = set(valid_page_ids)
    element_ids = set(valid_element_ids)
    table_ids = set(valid_table_ids)
    for region in manifest.regions:
        _validate_region(region, page_ids=page_ids, element_ids=element_ids, table_ids=table_ids)


def high_quality_required(
    *,
    validation_failed: bool,
    confidence: float,
    document_family: str,
    quality_flags: dict[str, object],
    user_marked_important: bool,
) -> bool:
    if validation_failed or user_marked_important:
        return True
    if confidence < 0.7:
        return True
    if document_family in HIGH_RISK_FAMILIES:
        return True
    if quality_flags.get("ocr_quality") == "poor":
        return True
    if quality_flags.get("document_type") == "ambiguous":
        return True
    return bool(quality_flags.get("needs_high_quality_pass"))


def _validate_region(
    region: SemanticRegionAnnotation,
    *,
    page_ids: set[UUID],
    element_ids: set[UUID],
    table_ids: set[UUID],
) -> None:
    if region.semantic_type not in ALLOWED_SEMANTIC_TYPES:
        raise SemanticAnnotationValidationError(
            f"Unsupported semantic type: {region.semantic_type}"
        )
    if region.granite_task is not None and region.granite_task not in ALLOWED_GRANITE_TASKS:
        raise SemanticAnnotationValidationError(f"Unsupported granite task: {region.granite_task}")
    _validate_grounding(region, page_ids=page_ids, element_ids=element_ids, table_ids=table_ids)


def _validate_grounding(
    region: SemanticRegionAnnotation,
    *,
    page_ids: set[UUID],
    element_ids: set[UUID],
    table_ids: set[UUID],
) -> None:
    grounding = region.grounding
    if grounding.kind == "unmatched_region":
        if region.semantic_type != "unmatched_region" or not region.review_required:
            raise SemanticAnnotationValidationError(
                "Ungrounded regions must use unmatched_region and be review-required."
            )
        return
    _require_grounded_id(grounding)
    if grounding.page_id is not None and grounding.page_id not in page_ids:
        raise SemanticAnnotationValidationError("Unknown Docling page grounding reference.")
    if grounding.element_id is not None and grounding.element_id not in element_ids:
        raise SemanticAnnotationValidationError("Unknown Docling element grounding reference.")
    if grounding.table_id is not None and grounding.table_id not in table_ids:
        raise SemanticAnnotationValidationError("Unknown Docling table grounding reference.")


def _require_grounded_id(grounding: SemanticGroundingRef) -> None:
    if grounding.kind == "page" and grounding.page_id is None:
        raise SemanticAnnotationValidationError("Page grounding requires page_id.")
    if grounding.kind == "element" and grounding.element_id is None:
        raise SemanticAnnotationValidationError("Element grounding requires element_id.")
    if grounding.kind == "table" and grounding.table_id is None:
        raise SemanticAnnotationValidationError("Table grounding requires table_id.")
