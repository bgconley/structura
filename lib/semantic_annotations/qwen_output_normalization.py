from __future__ import annotations

import re
import unicodedata

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
    "service_record",
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
    "service_record_line_item_table",
    "denial_or_coverage_decision",
    "appeal_or_next_steps",
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
_TARGET_SCHEMAS = {"receipt", "invoice", "medical_eob"}
_MAX_MODEL_OUTPUT_REGIONS = 6
_PRIORITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


def validated_model_output_payload(
    response: VisionGenerateResponse,
    *,
    source: ExtractionSourceDocument,
) -> dict[str, object]:
    payload = _normalized_model_output_payload(dict(response.normalized_json), source=source)
    try:
        Draft202012Validator(semantic_annotation_model_output_schema()).validate(payload)
    except ValidationError as exc:
        raise ModelProtocolError(
            f"semantic annotation model output failed schema validation: {exc.message}"
        ) from exc
    return payload


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
) -> dict[str, object]:
    if isinstance(payload.get("pages"), list) and isinstance(payload.get("regions"), list):
        return payload
    page_annotations = payload.get("page_annotations")
    if isinstance(page_annotations, list):
        return _payload_from_page_annotations(payload, source=source)
    return payload


def _payload_from_page_annotations(
    payload: dict[str, object],
    *,
    source: ExtractionSourceDocument,
) -> dict[str, object]:
    page_by_id = {str(page.page_id): page for page in source.pages}
    pages: list[dict[str, object]] = []
    regions: list[dict[str, object]] = []
    needs_high_quality_pass = False
    for item in payload["page_annotations"]:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id") or "")
        page = page_by_id.get(page_id)
        if page is None:
            raise ModelProtocolError("semantic page_annotations output referenced unknown page_id.")
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
            )
        )
        regions.extend(normalized_regions)
    regions = _select_regions_for_contract(regions)
    return {
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
) -> dict[str, object]:
    has_structured_targets = any(
        region.get("granite_task") not in {None, "ignore"} for region in page_regions
    )
    escalation_reasons = _normalized_escalation_reasons(item.get("escalation_reasons"))
    if page_needs_high_quality:
        escalation_reasons = _append_unique(escalation_reasons, "validation_sensitive")
    confidence = _average_confidence(page_regions)
    return {
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
    granite_task = _granite_task_or_none(item.get("granite_task"))
    target_schema = _target_schema_or_none(item.get("target_schema"))
    expected_fields = expected_fields_from_json(item.get("expected_fields"))
    confidence = _confidence_or_none(item.get("confidence"))
    return {
        "semantic_type": _normalized_choice(item.get("semantic_type"), _SEMANTIC_TYPES)
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
    fields = set(expected_fields)
    if fields & {"request_status", "denial_reason", "appeal_deadline", "care_requested"}:
        return "denial_or_coverage_decision"
    if fields & {"patient_responsibility", "plan_paid", "allowed_amount", "amount_billed"}:
        return "patient_responsibility_summary"
    if target_schema == "invoice":
        return "billing_summary"
    if target_schema == "receipt":
        return "payment_summary"
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


def _append_unique(values: list[str], value: str) -> list[str]:
    if value not in values and len(values) < 4:
        return [*values, value]
    return values


def _average_confidence(regions: list[dict[str, object]]) -> float | None:
    values = [
        float(region["confidence"])
        for region in regions
        if isinstance(region.get("confidence"), int | float)
    ]
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
