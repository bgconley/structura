from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


def normalize_granite_region_output(
    *,
    document_id: UUID,
    schema_name: str,
    model_output_schema_name: str | None,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_payload = _unwrapped_payload(payload)
    if model_output_schema_name == "granite_invoice_line_items.v1":
        return _invoice_line_items_output(document_id, model_payload)
    if model_output_schema_name == "granite_payment_summary.v1":
        return _invoice_payment_output(document_id, model_payload)
    if model_output_schema_name == "granite_medical_service_lines.v1":
        return _medical_service_lines_output(document_id, model_payload)
    if schema_name == "invoice" and _has_flat_invoice_line_items(model_payload):
        return _invoice_line_items_output(document_id, model_payload)
    return dict(payload), {"mapper": None, "repairs": [], "rejected_fields": []}


def invoice_line_item_dicts_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("line_items"), list):
        return _canonical_invoice_line_items(payload["line_items"])
    return _flat_invoice_line_items(payload)


def invoice_payment_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payment = _first_payment(payload)
    amount = _money(payment.get("amount") or payload.get("amount"))
    summary = {
        key: value
        for key, value in {
            "card_number": payment.get("card_number") or payload.get("card_number"),
            "merchant_id": payment.get("merchant_id") or payload.get("merchant_id"),
            "terminal_id": payment.get("terminal_id") or payload.get("terminal_id"),
            "auth_code": payment.get("auth_code") or payload.get("auth_code"),
            "auth_mode": payment.get("auth_mode") or payload.get("auth_mode"),
            "application_name": payment.get("application_name") or payload.get("application_name"),
        }.items()
        if value not in (None, "")
    }
    return {
        "invoice_number": payload.get("invoice_no") or payload.get("invoice_number"),
        "amount_paid": amount,
        "payment_summary": summary,
    }


def _invoice_line_items_output(
    document_id: UUID,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    line_items = invoice_line_item_dicts_from_payload(payload)
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    normalized: dict[str, Any] = {
        "schema_name": "invoice",
        "schema_version": "v1",
        "document_id": str(document_id),
        "line_items": line_items,
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    totals = _invoice_totals(payload)
    if totals:
        normalized["totals"] = totals
    return normalized, {
        "mapper": "granite_invoice_line_items.v1",
        "repairs": ["mapped_model_output_to_canonical_invoice_line_items"],
        "rejected_fields": _rejected_fields(
            payload,
            {"line_items", "totals", "confidence"},
        ),
    }


def _invoice_payment_output(
    document_id: UUID,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = invoice_payment_summary_from_payload(payload)
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    normalized: dict[str, Any] = {
        "schema_name": "invoice",
        "schema_version": "v1",
        "document_id": str(document_id),
        "invoice": {},
        "totals": {},
        "metadata": {},
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if summary.get("invoice_number"):
        normalized["invoice"]["invoice_number"] = summary["invoice_number"]
    if summary.get("amount_paid"):
        normalized["totals"]["amount_paid"] = summary["amount_paid"]
    if summary.get("payment_summary"):
        normalized["metadata"]["payment_summary"] = summary["payment_summary"]
    return normalized, {
        "mapper": "granite_payment_summary.v1",
        "repairs": ["mapped_model_output_to_canonical_invoice_payment_summary"],
        "rejected_fields": _rejected_fields(
            payload,
            {"invoice_no", "amount", "payments", "confidence"},
        ),
    }


def _medical_service_lines_output(
    document_id: UUID,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    return (
        {
            "schema_name": "medical_eob",
            "schema_version": "v1",
            "document_id": str(document_id),
            "service_lines": payload.get("service_lines") or [],
            "confidence": confidence,
            "created_at": datetime.now(UTC).isoformat(),
        },
        {
            "mapper": "granite_medical_service_lines.v1",
            "repairs": ["mapped_model_output_to_canonical_medical_service_lines"],
            "rejected_fields": _rejected_fields(payload, {"service_lines", "confidence"}),
        },
    )


def _canonical_invoice_line_items(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("description"):
            continue
        amount = _money(item.get("amount"))
        normalized.append(
            {
                "ordinal": int(item.get("ordinal") or len(normalized) + 1),
                "description": str(item["description"]),
                **({"quantity": _number(item.get("quantity"))} if item.get("quantity") else {}),
                **({"unit": item.get("unit")} if item.get("unit") else {}),
                **(
                    {"unit_price": _money(item.get("unit_price"))} if item.get("unit_price") else {}
                ),
                **({"amount": amount} if amount else {}),
                **(
                    {"category_hint": item.get("category_hint")}
                    if item.get("category_hint")
                    else {}
                ),
                "evidence": [_evidence(item.get("source_text") or item["description"])],
            }
        )
    return normalized


def _flat_invoice_line_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    service_descriptions = _string_list(payload.get("service_description"))
    parts = _string_list(payload.get("parts"))
    labor_costs = _string_list(payload.get("labor_cost"))
    parts_costs = _string_list(payload.get("parts_cost"))
    items: list[dict[str, Any]] = []
    for index, description in enumerate(service_descriptions):
        amount = _money(labor_costs[index] if index < len(labor_costs) else None)
        items.append(_line_item(len(items) + 1, description, amount, "service"))
    for index, description in enumerate(parts):
        amount = _money(parts_costs[index] if index < len(parts_costs) else None)
        items.append(_line_item(len(items) + 1, description, amount, "part"))
    return items


def _line_item(
    ordinal: int,
    description: str,
    amount: dict[str, Any] | None,
    category_hint: str,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ordinal": ordinal,
        "description": description,
        "category_hint": category_hint,
        "evidence": [_evidence(description)],
    }
    if amount:
        item["amount"] = amount
    return item


def _invoice_totals(payload: dict[str, Any]) -> dict[str, Any]:
    raw_totals = payload.get("totals")
    totals: dict[str, Any] = raw_totals if isinstance(raw_totals, dict) else {}
    result: dict[str, Any] = {}
    for source_key, target_key in (
        ("subtotal", "subtotal"),
        ("tax_total", "tax_total"),
        ("total", "total"),
    ):
        amount = _money(totals.get(source_key))
        if amount:
            result[target_key] = amount
    if not result:
        total_values = _string_list(payload.get("total_amount"))
        if total_values:
            amount = _money(total_values[0])
            if amount:
                result["total"] = amount
    return result


def _first_payment(payload: dict[str, Any]) -> dict[str, Any]:
    payments = payload.get("payments")
    if isinstance(payments, list):
        first = next((item for item in payments if isinstance(item, dict)), None)
        if first is not None:
            return first
    return {}


def _has_flat_invoice_line_items(payload: dict[str, Any]) -> bool:
    return any(
        key in payload for key in ("service_description", "parts", "labor_cost", "parts_cost")
    )


def _unwrapped_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = payload.get("normalized")
    if isinstance(normalized, dict):
        return normalized
    return payload


def _money(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("amount") is not None:
        return {"amount": float(value["amount"]), "currency": value.get("currency") or "USD"}
    amount = _number(value)
    if amount is None:
        return None
    return {"amount": amount, "currency": "USD"}


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
        if match:
            return float(match.group(0).replace(",", ""))
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _evidence(source_text: object) -> dict[str, Any]:
    text = str(source_text).strip()
    return {
        "page_number": 1,
        "source_engine": "granite_vision_3b",
        "source_text": text,
        "confidence": 0.72,
    }


def _rejected_fields(payload: dict[str, Any], accepted: set[str]) -> list[str]:
    return sorted(key for key in payload if key not in accepted)
