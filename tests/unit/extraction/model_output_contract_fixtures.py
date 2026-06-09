from __future__ import annotations

from typing import Any


def confidence(
    overall: float | None = 0.74,
    *,
    schema_fit: float | None = 0.7,
    table_structure: float | None = None,
) -> dict[str, Any]:
    confidence_json: dict[str, Any] = {"overall": overall, "schema_fit": schema_fit}
    if table_structure is not None:
        confidence_json["table_structure"] = table_structure
    return confidence_json


def seller_info_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "seller_name": None,
        "property_address": None,
        "title_company": None,
        "file_number": None,
        "closing_date": None,
        "confidence": confidence(),
    }
    payload.update(overrides)
    return payload


def generic_field(name: str, value: Any, *, source_text: str | None = None) -> dict[str, Any]:
    rendered_source = (
        source_text if source_text is not None else (None if value is None else str(value))
    )
    return {
        "name": name,
        "value": value,
        "source_text": rendered_source,
        "confidence": 0.74,
    }


def receipt_payment_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "merchant_name": None,
        "transaction_date": None,
        "subtotal": None,
        "tax": None,
        "tip": None,
        "discount_total": None,
        "total": None,
        "payment_method": None,
        "confidence": confidence(),
    }
    payload.update(overrides)
    return payload


def invoice_line_item(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ordinal": None,
        "description": "Line item",
        "quantity": None,
        "unit": None,
        "unit_price": None,
        "amount": None,
        "category_hint": None,
        "row_index": None,
        "table_id": None,
        "page_number": None,
    }
    item.update(overrides)
    return item


def invoice_totals(**overrides: Any) -> dict[str, Any]:
    totals: dict[str, Any] = {
        "subtotal": None,
        "tax_total": None,
        "shipping_total": None,
        "discount_total": None,
        "total": None,
    }
    totals.update(overrides)
    return totals


def invoice_line_items_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "line_items": [invoice_line_item(**row) for row in rows],
        "totals": invoice_totals(),
        "confidence": confidence(table_structure=0.8),
    }


def receipt_line_item(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ordinal": None,
        "description": "Line item",
        "quantity": None,
        "unit": None,
        "unit_price": None,
        "discount": None,
        "amount": None,
        "sku": None,
        "tax_category_hint": None,
        "category_hint": None,
        "row_index": None,
        "table_id": None,
        "page_number": None,
    }
    item.update(overrides)
    return item


def receipt_totals(**overrides: Any) -> dict[str, Any]:
    totals: dict[str, Any] = {"subtotal": None, "tax": None, "total": None}
    totals.update(overrides)
    return totals
