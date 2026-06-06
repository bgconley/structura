from __future__ import annotations

from typing import Any

from lib.extraction.evidence_concretizer import evidence_ref_from_context
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.line_item_provenance import line_item_evidence
from lib.extraction.model_output_value_parsing import money_value, number_value

NON_LINE_ITEM_HEADINGS = {
    "customer information",
    "transaction information",
    "vehicle information",
    "service department hours",
    "payment information",
}

INVOICE_LINE_ITEM_KEYS = frozenset(
    {
        "ordinal",
        "description",
        "quantity",
        "unit",
        "unit_price",
        "amount",
        "category_hint",
        "row_index",
        "table_id",
        "page_number",
    }
)

RECEIPT_LINE_ITEM_KEYS = frozenset(
    {
        "ordinal",
        "description",
        "quantity",
        "unit",
        "unit_price",
        "discount",
        "amount",
        "sku",
        "tax_category_hint",
        "category_hint",
        "row_index",
        "table_id",
        "page_number",
    }
)

RETAIL_ORDER_LINE_ITEM_KEYS = frozenset(
    {
        "description",
        "quantity",
        "unit_price",
        "amount",
        "source_text",
    }
)

SERVICE_RECORD_LINE_ITEM_KEYS = frozenset(
    {
        "ordinal",
        "description",
        "service_description",
        "labor_operation",
        "part_number",
        "quantity",
        "unit",
        "unit_price",
        "line_total",
        "amount",
        "category_hint",
        "row_index",
        "table_id",
        "page_number",
    }
)


def simple_line_item(
    ordinal: int,
    description: str,
    amount: dict[str, Any] | None,
    category_hint: str,
    *,
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ordinal": ordinal,
        "description": description,
        "category_hint": category_hint,
        "evidence": [_evidence(description, evidence_context)],
    }
    if amount:
        item["amount"] = amount
    return item


def service_record_line_item(
    *,
    ordinal: int,
    description: str,
    category_hint: str,
    quantity: Any,
    unit: Any,
    unit_price: Any,
    amount: Any,
    source_text: str,
    evidence_context: EvidenceContext | None,
    code: Any = None,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "ordinal": ordinal,
        "description": description,
        "category_hint": category_hint,
        "evidence": [_evidence(source_text, evidence_context)],
    }
    parsed_quantity = number_value(quantity)
    parsed_unit_price = money_value(unit_price)
    parsed_amount = money_value(amount)
    if parsed_quantity is not None:
        normalized["quantity"] = parsed_quantity
    if code not in (None, ""):
        normalized["sku"] = str(code)
    if unit not in (None, ""):
        normalized["unit"] = str(unit)
    if parsed_unit_price is not None:
        normalized["unit_price"] = parsed_unit_price
    if parsed_amount is not None:
        normalized["amount"] = parsed_amount
    return normalized


def join_source_text(description: str, **parts: Any) -> str:
    values = [description]
    for key, value in parts.items():
        if value not in (None, ""):
            values.append(f"{key}: {value}")
    return " | ".join(values)


def line_item_description(
    item: dict[str, Any],
    *,
    keys: tuple[str, ...] = ("description",),
) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def line_item_amount(
    item: dict[str, Any],
    *,
    keys: tuple[str, ...] = ("amount",),
) -> dict[str, Any] | None:
    for key in keys:
        amount = money_value(item.get(key))
        if amount is not None:
            return amount
    return None


def is_non_line_item_heading(
    item: dict[str, Any],
    description: str,
    *,
    category_keys: tuple[str, ...] = ("category_hint",),
) -> bool:
    normalized_description = description.strip().lower()
    category = next((item.get(key) for key in category_keys if item.get(key)), None)
    normalized_category = str(category).strip().lower() if category else ""
    return (
        normalized_description in NON_LINE_ITEM_HEADINGS
        or normalized_category in NON_LINE_ITEM_HEADINGS
    )


def line_item_source_text(item: dict[str, Any], description: str) -> str:
    parts = [description]
    for key in ("parts", "service_notes", "service_provider", "service_location"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{key}: {value.strip()}")
    return " | ".join(parts)


def canonical_line_item_evidence(
    item: dict[str, Any],
    description: str,
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    return line_item_evidence(item, line_item_source_text(item, description), evidence_context)


def item_matches_contract(item: dict[str, Any], allowed_keys: frozenset[str]) -> bool:
    return set(item).issubset(allowed_keys)


def _evidence(
    source_text: object,
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    text = str(source_text or "").strip()
    if evidence_context is not None:
        return evidence_ref_from_context(evidence_context=evidence_context, source_text=text)
    return {
        "source_engine": "granite_vision_3b",
        "source_text": text,
        "confidence": 0.72,
    }
