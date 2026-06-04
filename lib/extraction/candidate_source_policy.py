from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

TITLE_DERIVED_COUNTERPARTY_REASON = "title_derived_merchant_seller_without_allowlist"

_COUNTERPARTY_FIELD_HINTS = ("merchant", "seller", "counterparty")
_ALLOW_TITLE_DERIVED_KEYS = (
    "allow_title_derived_merchant_seller",
    "allowTitleDerivedMerchantSeller",
)
_SOURCE_KEYS = ("source", "sourceKind", "source_kind", "sourceEngine", "source_engine")


def title_derived_counterparty_rejection_reason(
    *,
    field_path: str,
    evidence: Sequence[Mapping[str, Any]],
    validation: Mapping[str, Any] | None,
    run_metadata: Mapping[str, Any] | None,
) -> str | None:
    if not _is_counterparty_field(field_path):
        return None
    if _title_derivation_allowed(validation) or _title_derivation_allowed(run_metadata):
        return None
    if any(_evidence_is_document_title(item) for item in evidence):
        return TITLE_DERIVED_COUNTERPARTY_REASON
    return None


def _is_counterparty_field(field_path: str) -> bool:
    normalized = _normalized_label(field_path)
    return any(hint in normalized for hint in _COUNTERPARTY_FIELD_HINTS)


def _title_derivation_allowed(mapping: Mapping[str, Any] | None) -> bool:
    if not mapping:
        return False
    return any(_bool_value(mapping.get(key)) for key in _ALLOW_TITLE_DERIVED_KEYS)


def _evidence_is_document_title(evidence: Mapping[str, Any]) -> bool:
    source = _normalized_label(_first_value(evidence, _SOURCE_KEYS))
    if source in {"document_title", "title"} or "document_title" in source:
        return True
    text_span = evidence.get("text_span") or evidence.get("textSpan")
    if isinstance(text_span, Mapping):
        basis = _normalized_label(text_span.get("basis"))
        return basis in {"document_title", "title"} or "document_title" in basis
    return False


def _first_value(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _normalized_label(value: object) -> str:
    label = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value or "").strip())
    label = re.sub(r"[^A-Za-z0-9]+", "_", label).lower()
    return "_".join(part for part in label.split("_") if part)
