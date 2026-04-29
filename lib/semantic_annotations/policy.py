from __future__ import annotations

import re
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
    "retail_order_line_item_table",
    "service_record_line_item_table",
    "receipt_payment_summary",
    "denial_or_coverage_decision",
    "appeal_or_next_steps",
    "seller_information_block",
    "escrow_summary",
    "mortgage_payment_summary",
    "dispute_transaction_table",
    "dispute_reason_block",
    "generic_form_kvp",
    "no_extraction_target",
    "unsupported_document_region",
    "tax_summary",
    "legal_clause",
    "contact_block",
    "vehicle_or_asset_block",
    "signature_block",
    "boilerplate",
    "unmatched_region",
    "unknown",
}

ALLOWED_TARGET_SCHEMAS = {"receipt", "invoice", "medical_eob", "document_observation"}
_EXPECTED_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

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
    manifest_page_ids = {page.page_id for page in manifest.pages}
    if len(manifest_page_ids) != len(manifest.pages):
        raise SemanticAnnotationValidationError("Semantic page annotations contain duplicates.")
    if manifest_page_ids != page_ids:
        raise SemanticAnnotationValidationError(
            "Semantic annotation page coverage must exactly match Docling pages."
        )
    seen_region_intents: set[tuple[object, ...]] = set()
    for region in manifest.regions:
        _validate_region(region, page_ids=page_ids, element_ids=element_ids, table_ids=table_ids)
        region_intent_key = _region_intent_key(region)
        if region_intent_key in seen_region_intents:
            raise SemanticAnnotationValidationError("Duplicate semantic region extraction intent.")
        seen_region_intents.add(region_intent_key)


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
    if region.target_schema is not None and region.target_schema not in ALLOWED_TARGET_SCHEMAS:
        raise SemanticAnnotationValidationError(
            f"Unsupported target schema: {region.target_schema}"
        )
    if region.granite_task == "ignore" and region.target_schema is not None:
        raise SemanticAnnotationValidationError(
            "Ignored semantic regions must not target a schema."
        )
    if region.granite_task not in {None, "ignore"} and region.target_schema is None:
        raise SemanticAnnotationValidationError("Granite extraction regions require target schema.")
    for field_name in region.expected_fields:
        if not _EXPECTED_FIELD_RE.fullmatch(field_name):
            raise SemanticAnnotationValidationError(
                f"Unsupported expected field name: {field_name}"
            )
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


def _region_intent_key(region: SemanticRegionAnnotation) -> tuple[object, ...]:
    return (
        region.semantic_type,
        region.granite_task,
        region.target_schema,
        tuple(sorted(region.expected_fields)),
        _grounding_key(region.grounding),
    )


def _grounding_key(grounding: SemanticGroundingRef) -> tuple[object, ...]:
    return (
        grounding.kind,
        grounding.page_id,
        grounding.element_id,
        grounding.table_id,
    )
