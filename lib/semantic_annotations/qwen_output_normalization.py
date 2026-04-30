from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from jsonschema import Draft202012Validator, ValidationError

from lib.extraction.models import ExtractionSourceDocument
from lib.model_runtime.contracts import VisionGenerateResponse
from lib.model_runtime.http_client import ModelProtocolError
from lib.semantic_annotations.schema import semantic_annotation_model_output_schema

_EXPECTED_FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DOCUMENT_TYPES = {
    "medical_eob",
    "insurance_denial",
    "medical_bill",
    "invoice",
    "receipt",
    "retail_order",
    "service_record",
    "real_estate_title",
    "mortgage_escrow_statement",
    "financial_dispute_form",
    "travel_receipt",
    "restaurant_receipt",
    "generic_form",
    "unsupported_document",
    "no_extraction_target",
    "legal",
    "tax",
    "financial",
    "other",
    "unknown",
}
_PAGE_ROLES = {
    "document_header",
    "claim_summary",
    "payment_summary",
    "line_items",
    "denial_or_decision",
    "instructions",
    "contact_or_identity",
    "terms_or_boilerplate",
    "signature_or_authorization",
    "image_or_figure",
    "mixed",
    "unknown",
}
_EXTRACTION_USEFULNESS = {"none", "low", "medium", "high", "unknown"}
_ESCALATION_REASONS = {
    "poor_ocr",
    "ambiguous_document_type",
    "missing_docling_grounding",
    "high_risk_domain",
    "low_confidence",
    "validation_sensitive",
    "unsupported_schema",
    "visual_degradation",
}
_SEMANTIC_TYPES = {
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
_PRIORITIES = {"low", "medium", "high", "critical"}
_GRANITE_TASKS = {"kvp", "tables_json", "tables_html", "tables_otsl", "ignore"}
_TARGET_SCHEMAS = {"receipt", "invoice", "medical_eob", "document_observation"}
_MAX_MODEL_OUTPUT_REGIONS = 12
_PRIORITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}
_DOCLING_TABLE_SIGNALS = {"none", "weak", "strong", "unknown"}
_SOURCE_SIGNALS = {"text", "table", "visual", "mixed"}
_COVERAGE_ROLES = {"primary", "continuation", "summary", "supporting", "boilerplate", "unknown"}
_EXTRACTION_SCOPES = {"table", "element", "page", "multi_page_group"}


@dataclass(frozen=True)
class ValidatedModelOutputPayload:
    payload: dict[str, object]
    normalization: dict[str, object]


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


def expected_fields_from_json(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    fields: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        field_name = unicodedata.normalize("NFKC", item).strip().lower()
        field_name = field_name.replace(" ", "_").replace("-", "_")
        if not field_name.isascii() or not _EXPECTED_FIELD_NAME_RE.fullmatch(field_name):
            continue
        if field_name not in seen:
            fields.append(field_name)
            seen.add(field_name)
    return tuple(fields)


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


def _canonical_payload_filtered_to_source(
    payload: dict[str, object],
    *,
    source: ExtractionSourceDocument,
) -> ValidatedModelOutputPayload:
    pages = payload.get("pages")
    regions = payload.get("regions")
    if not isinstance(pages, list) or not isinstance(regions, list):
        return ValidatedModelOutputPayload(payload=payload, normalization={})

    valid_page_ids = {str(page.page_id) for page in source.pages}

    kept_pages: list[object] = []
    dropped_page_ids: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            kept_pages.append(page)
            continue
        page_id = str(page.get("page_id") or "")
        if page_id in valid_page_ids:
            kept_pages.append(page)
        elif page_id:
            dropped_page_ids.append(page_id)

    kept_regions: list[object] = []
    dropped_region_count = 0
    for region in regions:
        if not isinstance(region, dict):
            kept_regions.append(region)
            continue
        if _region_grounding_is_within_source_window(
            region,
            valid_page_ids=valid_page_ids,
        ):
            kept_regions.append(region)
        else:
            dropped_region_count += 1

    if not dropped_page_ids and not dropped_region_count:
        return ValidatedModelOutputPayload(payload=payload, normalization={})

    normalized_payload = dict(payload)
    normalized_payload["pages"] = kept_pages
    normalized_payload["regions"] = kept_regions
    normalization: dict[str, object] = {
        "output_scope_filter_policy": "filter_to_requested_docling_pages",
    }
    if dropped_page_ids:
        normalization["out_of_window_pages_dropped"] = len(dropped_page_ids)
        normalization["out_of_window_page_ids"] = dropped_page_ids[:12]
    if dropped_region_count:
        normalization["out_of_window_regions_dropped"] = dropped_region_count
    return ValidatedModelOutputPayload(payload=normalized_payload, normalization=normalization)


def _region_grounding_is_within_source_window(
    region: dict[str, object],
    *,
    valid_page_ids: set[str],
) -> bool:
    grounding = region.get("grounding")
    if not isinstance(grounding, dict):
        return True

    page_id = str(grounding.get("page_id") or "")
    if page_id and page_id not in valid_page_ids:
        return False
    return True


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


def _merge_reasons(first: object, second: object) -> list[str]:
    reasons: list[str] = []
    for collection in (first, second):
        if not isinstance(collection, list):
            continue
        for item in collection:
            reason = _normalized_choice(item, _ESCALATION_REASONS)
            if reason and reason not in reasons:
                reasons.append(reason)
    return reasons[:4]


def _select_regions_for_contract(regions: list[dict[str, object]]) -> list[dict[str, object]]:
    ranked = sorted(
        enumerate(regions),
        key=lambda item: _region_rank(item[1], item[0]),
    )
    return [region for _, region in ranked[:_MAX_MODEL_OUTPUT_REGIONS]]


def _region_rank(region: dict[str, object], original_index: int) -> tuple[object, ...]:
    priority = str(region.get("priority") or "medium")
    confidence = region.get("confidence")
    return (
        -_PRIORITY_RANK.get(priority, 1),
        1 if region.get("granite_task") == "ignore" else 0,
        -float(confidence) if isinstance(confidence, int | float) else 0.0,
        original_index,
    )


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
        "document_type_hint": _document_type_or_none(item.get("document_type_hint"))
        or _document_type_or_none(source.family),
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
            "page_id": str(grounding["page_id"]) if grounding.get("page_id") else None,
            "element_id": (str(grounding["element_id"]) if grounding.get("element_id") else None),
            "table_id": str(grounding["table_id"]) if grounding.get("table_id") else None,
        }
    if item.get("table_id"):
        return {
            "kind": "table",
            "page_id": None,
            "element_id": None,
            "table_id": str(item["table_id"]),
        }
    if item.get("element_id"):
        return {
            "kind": "element",
            "page_id": None,
            "element_id": str(item["element_id"]),
            "table_id": None,
        }
    if item.get("tableId"):
        return {
            "kind": "table",
            "page_id": None,
            "element_id": None,
            "table_id": str(item["tableId"]),
        }
    if item.get("elementId"):
        return {
            "kind": "element",
            "page_id": None,
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
    return (
        _document_type_or_none(payload.get("document_type"))
        or _document_type_or_none(
            source.family,
        )
        or "other"
    )


def _document_type_or_none(value: object) -> str | None:
    normalized = _normalized_choice(value, _DOCUMENT_TYPES)
    if normalized:
        return normalized
    if not isinstance(value, str):
        return None
    mapped = {
        "eob": "medical_eob",
        "denial": "insurance_denial",
        "insurance": "insurance_denial",
        "medical": "medical_bill",
        "bill": "invoice",
        "service": "service_record",
    }.get(value.strip().lower())
    return mapped


def _document_type_candidates(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    candidates: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        document_type = _document_type_or_none(
            _first_present(item, "document_type", "documentType")
        )
        if document_type is None:
            continue
        candidates.append(
            {
                "document_type": document_type,
                "confidence": _confidence_or_none(item.get("confidence")),
                "evidence_terms": _bounded_string_list(
                    _first_present(item, "evidence_terms", "evidenceTerms"),
                    limit=8,
                    max_length=64,
                ),
                "reason": _optional_string(item.get("reason")),
            }
        )
        if len(candidates) >= 4:
            break
    return candidates


def _normalized_page_planner_fields(item: dict[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    hints = [
        hint
        for hint in (
            _document_type_or_none(value)
            for value in _list_value(_first_present(item, "page_family_hints", "pageFamilyHints"))
        )
        if hint is not None
    ][:3]
    if hints:
        fields["page_family_hints"] = hints
    continuation_group = _optional_string(
        _first_present(item, "continuation_group", "continuationGroup")
    )
    if continuation_group is not None:
        fields["continuation_group"] = continuation_group[:80]
    table_signal = _normalized_choice(
        _first_present(item, "docling_table_signal", "doclingTableSignal"),
        _DOCLING_TABLE_SIGNALS,
    )
    if table_signal is not None:
        fields["docling_table_signal"] = table_signal
    cross_page = _optional_bool(
        _first_present(item, "requires_cross_page_context", "requiresCrossPageContext")
    )
    if cross_page is not None:
        fields["requires_cross_page_context"] = cross_page
    count_hint = _bounded_int(
        _first_present(item, "material_region_count_hint", "materialRegionCountHint"),
        minimum=0,
        maximum=12,
    )
    if count_hint is not None:
        fields["material_region_count_hint"] = count_hint
    return fields


def _normalized_region_planner_fields(item: dict[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, allowed in (
        ("importance", _PRIORITIES),
        ("source_signal", _SOURCE_SIGNALS),
        ("coverage_role", _COVERAGE_ROLES),
        ("extraction_scope", _EXTRACTION_SCOPES),
    ):
        value = _normalized_choice(_first_present(item, key, _camel_case(key)), allowed)
        if value is not None:
            fields[key] = value
    requires_full_page_image = _optional_bool(
        _first_present(item, "requires_full_page_image", "requiresFullPageImage")
    )
    if requires_full_page_image is not None:
        fields["requires_full_page_image"] = requires_full_page_image
    continuation_group = _optional_string(
        _first_present(item, "continuation_group", "continuationGroup")
    )
    if continuation_group is not None:
        fields["continuation_group"] = continuation_group[:80]
    for key in ("must_extract_reason", "negative_routing_reason"):
        value = _optional_string(_first_present(item, key, _camel_case(key)))
        if value is not None:
            fields[key] = value[:180]
    min_expected_items = _bounded_int(
        _first_present(item, "min_expected_items", "minExpectedItems"),
        minimum=0,
        maximum=500,
    )
    if min_expected_items is not None:
        fields["min_expected_items"] = min_expected_items
    visual_bbox_hint = _visual_bbox_hint(_first_present(item, "visual_bbox_hint", "visualBboxHint"))
    if visual_bbox_hint is not None:
        fields["visual_bbox_hint"] = visual_bbox_hint
    return fields


def _granite_task_or_none(value: object) -> str | None:
    return _normalized_choice(value, _GRANITE_TASKS)


def _target_schema_or_none(value: object) -> str | None:
    normalized = _normalized_choice(value, _TARGET_SCHEMAS)
    if normalized:
        return normalized
    if not isinstance(value, str):
        return None
    mapped = {
        "insurance_denial": "medical_eob",
        "medical_bill": "medical_eob",
        "service_record": "receipt",
        "retail_order": "receipt",
        "travel_receipt": "receipt",
        "restaurant_receipt": "receipt",
        "real_estate_title": "document_observation",
        "mortgage_escrow_statement": "document_observation",
        "financial_dispute_form": "document_observation",
        "generic_form": "document_observation",
        "unsupported_document": "document_observation",
    }.get(value.strip().lower())
    return mapped


def _inferred_semantic_type(
    *,
    granite_task: str | None,
    target_schema: str | None,
    expected_fields: tuple[str, ...],
) -> str:
    if granite_task == "ignore":
        return "boilerplate"
    if granite_task in {"tables_json", "tables_html", "tables_otsl"}:
        if target_schema == "invoice":
            return "invoice_line_item_table"
        if target_schema == "receipt":
            return "receipt_line_item_table"
        if target_schema == "medical_eob":
            return "covered_services_line_item_table"
        if target_schema == "document_observation":
            return "generic_form_kvp"
    fields = set(expected_fields)
    if fields & {"request_status", "denial_reason", "appeal_deadline", "care_requested"}:
        return "denial_or_coverage_decision"
    if fields & {"patient_responsibility", "plan_paid", "allowed_amount", "amount_billed"}:
        return "patient_responsibility_summary"
    if target_schema == "invoice":
        return "billing_summary"
    if target_schema == "receipt":
        return "payment_summary"
    if target_schema == "document_observation":
        return "generic_form_kvp"
    return "unknown"


def _normalized_escalation_reasons(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    reasons: list[str] = []
    for item in value:
        reason = _normalized_choice(item, _ESCALATION_REASONS)
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons[:4]


def _bounded_string_list(value: object, *, limit: int, max_length: int) -> list[str]:
    values: list[str] = []
    for item in _list_value(value):
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if not stripped:
            continue
        values.append(stripped[:max_length])
        if len(values) >= limit:
            break
    return values


def _list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _first_present(item: dict[str, object], *keys: str) -> object:
    for key in keys:
        if key in item:
            return item[key]
    return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _bounded_int(value: object, *, minimum: int, maximum: int) -> int | None:
    if not isinstance(value, int):
        return None
    return max(minimum, min(value, maximum))


def _visual_bbox_hint(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    try:
        bbox = {key: max(0, min(int(value[key]), 1000)) for key in ("x1", "y1", "x2", "y2")}
    except (KeyError, TypeError, ValueError):
        return None
    if bbox["x2"] < bbox["x1"] or bbox["y2"] < bbox["y1"]:
        return None
    return bbox


def _camel_case(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def _append_unique(values: list[str], value: str) -> list[str]:
    if value not in values and len(values) < 4:
        return [*values, value]
    return values


def _average_confidence(regions: list[dict[str, object]]) -> float | None:
    values: list[float] = []
    for region in regions:
        confidence = region.get("confidence")
        if isinstance(confidence, int | float):
            values.append(float(confidence))
    if not values:
        return None
    return sum(values) / len(values)


def _confidence_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return max(0.0, min(float(value), 1.0))
    return None


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _normalized_choice(value: object, allowed: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    if normalized in allowed:
        return normalized
    return None
