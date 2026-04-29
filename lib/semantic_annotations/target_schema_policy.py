from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTED_TARGET_SCHEMAS = frozenset({"invoice", "medical_eob", "receipt"})


def preferred_target_schema(
    *,
    document_family: str | None,
    document_metadata: Mapping[str, Any],
    document_type_hint: str | None,
    semantic_type: str | None,
    model_target_schema: str | None,
) -> str | None:
    return (
        classified_document_target_schema(document_family, document_metadata)
        or target_schema_from_document_hint(document_type_hint)
        or target_schema_from_semantic_type(semantic_type)
        or target_schema_from_document_hint(model_target_schema)
        or target_schema_from_document_hint(document_family)
    )


def classified_document_target_schema(
    document_family: str | None,
    document_metadata: Mapping[str, Any],
) -> str | None:
    phase4 = document_metadata.get("phase4")
    if not isinstance(phase4, Mapping):
        return None
    classification = phase4.get("classification")
    if not isinstance(classification, Mapping):
        return None
    classified_family = classification.get("family") or document_family
    return target_schema_from_document_hint(str(classified_family) if classified_family else None)


def target_schema_from_document_hint(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in SUPPORTED_TARGET_SCHEMAS:
        return normalized
    if normalized in {"insurance_denial", "medical_bill", "medical_claim"}:
        return "medical_eob"
    if normalized in {"service_record", "payment_receipt"}:
        return "receipt"
    return None


def target_schema_from_semantic_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized.startswith("invoice_") or normalized == "invoice":
        return "invoice"
    if normalized.startswith("receipt_") or normalized == "receipt":
        return "receipt"
    if (
        normalized.startswith("medical_")
        or normalized.startswith("claim_")
        or normalized.startswith("eob_")
        or "medical_eob" in normalized
    ):
        return "medical_eob"
    return None
