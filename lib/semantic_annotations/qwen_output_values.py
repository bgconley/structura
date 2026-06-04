from __future__ import annotations

import re
import unicodedata

EXPECTED_FIELD_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
DOCUMENT_TYPES = {
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
PAGE_ROLES = {
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
EXTRACTION_USEFULNESS = {"none", "low", "medium", "high", "unknown"}
ESCALATION_REASONS = {
    "poor_ocr",
    "ambiguous_document_type",
    "missing_docling_grounding",
    "high_risk_domain",
    "low_confidence",
    "validation_sensitive",
    "unsupported_schema",
    "visual_degradation",
}
SEMANTIC_TYPES = {
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
PRIORITIES = {"low", "medium", "high", "critical"}
GRANITE_TASKS = {"kvp", "tables_json", "tables_html", "tables_otsl", "ignore"}
TARGET_SCHEMAS = {"receipt", "invoice", "medical_eob", "document_observation"}
MAX_MODEL_OUTPUT_REGIONS = 12
PRIORITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}
DOCLING_TABLE_SIGNALS = {"none", "weak", "strong", "unknown"}
SOURCE_SIGNALS = {"text", "table", "visual", "mixed"}
COVERAGE_ROLES = {"primary", "continuation", "summary", "supporting", "boilerplate", "unknown"}
EXTRACTION_SCOPES = {"table", "element", "page", "multi_page_group"}


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
        if not field_name.isascii() or not EXPECTED_FIELD_NAME_RE.fullmatch(field_name):
            continue
        if field_name not in seen:
            fields.append(field_name)
            seen.add(field_name)
    return tuple(fields)


def merge_reasons(first: object, second: object) -> list[str]:
    reasons: list[str] = []
    for collection in (first, second):
        if not isinstance(collection, list):
            continue
        for item in collection:
            reason = normalized_choice(item, ESCALATION_REASONS)
            if reason and reason not in reasons:
                reasons.append(reason)
    return reasons[:4]


def select_regions_for_contract(regions: list[dict[str, object]]) -> list[dict[str, object]]:
    ranked = sorted(
        enumerate(regions),
        key=lambda item: _region_rank(item[1], item[0]),
    )
    return [region for _, region in ranked[:MAX_MODEL_OUTPUT_REGIONS]]


def _region_rank(region: dict[str, object], original_index: int) -> tuple[object, ...]:
    priority = str(region.get("priority") or "medium")
    confidence = region.get("confidence")
    return (
        -PRIORITY_RANK.get(priority, 1),
        1 if region.get("granite_task") == "ignore" else 0,
        -float(confidence) if isinstance(confidence, int | float) else 0.0,
        original_index,
    )


def document_type_or_none(value: object) -> str | None:
    normalized = normalized_choice(value, DOCUMENT_TYPES)
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


def document_type_candidates(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    candidates: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        document_type = document_type_or_none(first_present(item, "document_type", "documentType"))
        if document_type is None:
            continue
        candidates.append(
            {
                "document_type": document_type,
                "confidence": confidence_or_none(item.get("confidence")),
                "evidence_terms": bounded_string_list(
                    first_present(item, "evidence_terms", "evidenceTerms"),
                    limit=8,
                    max_length=64,
                ),
                "reason": optional_string(item.get("reason")),
            }
        )
        if len(candidates) >= 4:
            break
    return candidates


def normalized_page_planner_fields(item: dict[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    hints = [
        hint
        for hint in (
            document_type_or_none(value)
            for value in list_value(first_present(item, "page_family_hints", "pageFamilyHints"))
        )
        if hint is not None
    ][:3]
    if hints:
        fields["page_family_hints"] = hints
    continuation_group = optional_string(
        first_present(item, "continuation_group", "continuationGroup")
    )
    if continuation_group is not None:
        fields["continuation_group"] = continuation_group[:80]
    table_signal = normalized_choice(
        first_present(item, "docling_table_signal", "doclingTableSignal"),
        DOCLING_TABLE_SIGNALS,
    )
    if table_signal is not None:
        fields["docling_table_signal"] = table_signal
    cross_page = optional_bool(
        first_present(item, "requires_cross_page_context", "requiresCrossPageContext")
    )
    if cross_page is not None:
        fields["requires_cross_page_context"] = cross_page
    count_hint = bounded_int(
        first_present(item, "material_region_count_hint", "materialRegionCountHint"),
        minimum=0,
        maximum=12,
    )
    if count_hint is not None:
        fields["material_region_count_hint"] = count_hint
    return fields


def normalized_region_planner_fields(item: dict[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, allowed in (
        ("importance", PRIORITIES),
        ("source_signal", SOURCE_SIGNALS),
        ("coverage_role", COVERAGE_ROLES),
        ("extraction_scope", EXTRACTION_SCOPES),
    ):
        value = normalized_choice(first_present(item, key, camel_case(key)), allowed)
        if value is not None:
            fields[key] = value
    requires_full_page_image = optional_bool(
        first_present(item, "requires_full_page_image", "requiresFullPageImage")
    )
    if requires_full_page_image is not None:
        fields["requires_full_page_image"] = requires_full_page_image
    continuation_group = optional_string(
        first_present(item, "continuation_group", "continuationGroup")
    )
    if continuation_group is not None:
        fields["continuation_group"] = continuation_group[:80]
    for key in ("must_extract_reason", "negative_routing_reason"):
        value = optional_string(first_present(item, key, camel_case(key)))
        if value is not None:
            fields[key] = value[:180]
    min_expected_items = bounded_int(
        first_present(item, "min_expected_items", "minExpectedItems"),
        minimum=0,
        maximum=500,
    )
    if min_expected_items is not None:
        fields["min_expected_items"] = min_expected_items
    visual_bbox_hint = _visual_bbox_hint(first_present(item, "visual_bbox_hint", "visualBboxHint"))
    if visual_bbox_hint is not None:
        fields["visual_bbox_hint"] = visual_bbox_hint
    return fields


def granite_task_or_none(value: object) -> str | None:
    return normalized_choice(value, GRANITE_TASKS)


def target_schema_or_none(value: object) -> str | None:
    normalized = normalized_choice(value, TARGET_SCHEMAS)
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


def inferred_semantic_type(
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


def normalized_escalation_reasons(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    reasons: list[str] = []
    for item in value:
        reason = normalized_choice(item, ESCALATION_REASONS)
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons[:4]


def bounded_string_list(value: object, *, limit: int, max_length: int) -> list[str]:
    values: list[str] = []
    for item in list_value(value):
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if not stripped:
            continue
        values.append(stripped[:max_length])
        if len(values) >= limit:
            break
    return values


def list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def first_present(item: dict[str, object], *keys: str) -> object:
    for key in keys:
        if key in item:
            return item[key]
    return None


def optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def bounded_int(value: object, *, minimum: int, maximum: int) -> int | None:
    if not isinstance(value, int):
        return None
    return max(minimum, min(value, maximum))


def camel_case(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def append_unique(values: list[str], value: str) -> list[str]:
    if value not in values and len(values) < 4:
        return [*values, value]
    return values


def average_confidence(regions: list[dict[str, object]]) -> float | None:
    values: list[float] = []
    for region in regions:
        confidence = region.get("confidence")
        if isinstance(confidence, int | float):
            values.append(float(confidence))
    if not values:
        return None
    return sum(values) / len(values)


def confidence_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return max(0.0, min(float(value), 1.0))
    return None


def optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def normalized_choice(value: object, allowed: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    if normalized in allowed:
        return normalized
    return None


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
