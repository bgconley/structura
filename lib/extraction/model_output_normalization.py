from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lib.extraction.evidence_concretizer import evidence_ref_from_context
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.region_envelope_projection import finalized_region_output

_NON_LINE_ITEM_HEADINGS = {
    "customer information",
    "transaction information",
    "vehicle information",
    "service department hours",
    "payment information",
}
_DROP_FLAT_OBSERVATION_KEYS = {
    "$schema",
    "$defs",
    "type",
    "properties",
    "required",
    "additionalproperties",
    "items",
    "title",
    "description",
    "schema_name",
    "schema_version",
    "document_id",
    "created_at",
    "metadata",
    "validation",
    "confidence",
    "prompt",
    "instructions",
}
_ECHO_PHRASES = (
    "return only",
    "json schema",
    "matching this schema",
    "do not copy these instructions",
    "semantic task from qwen",
    "<tables_json>",
    "additionalproperties",
)


def normalize_granite_region_output(
    *,
    document_id: UUID,
    schema_name: str,
    model_output_schema_name: str | None,
    payload: Any,
    evidence_context: EvidenceContext | None = None,
    semantic_type: str | None = None,
    target_schema: str | None = None,
    resolved_document_type: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_payload, wrapper_repairs = _unwrapped_payload(payload)

    def finalize(
        normalized: dict[str, Any],
        metadata: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return _finalized_output(
            normalized,
            metadata,
            wrapper_repairs,
            evidence_context,
            model_output_schema_name=model_output_schema_name,
            semantic_type=semantic_type,
            target_schema=target_schema or schema_name,
            resolved_document_type=resolved_document_type,
        )

    if model_output_schema_name == "granite_invoice_line_items.v1":
        normalized, metadata = _invoice_line_items_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_payment_summary.v1":
        normalized, metadata = _invoice_payment_output(document_id, model_payload)
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_medical_service_lines.v1":
        normalized, metadata = _medical_service_lines_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    if model_output_schema_name in {
        "granite_receipt_line_items.v1",
        "granite_retail_order.v1",
    }:
        normalized, metadata = _receipt_line_items_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        metadata["mapper"] = model_output_schema_name
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_service_record_line_items.v1":
        normalized, metadata = _service_record_line_items_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_receipt_payment_summary.v1":
        normalized, metadata = _receipt_payment_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    if model_output_schema_name == "granite_healthcare_coverage_decision.v1":
        normalized, metadata = _healthcare_coverage_decision_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    if schema_name == "document_observation" or model_output_schema_name in {
        "granite_real_estate_title_seller_info.v1",
        "granite_mortgage_escrow_statement.v1",
        "granite_dispute_form.v1",
        "granite_generic_kvp.v1",
    }:
        normalized, metadata = _document_observation_output(
            document_id,
            model_payload,
            model_output_schema_name=model_output_schema_name,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    if schema_name == "invoice" and _has_flat_invoice_line_items(model_payload):
        normalized, metadata = _invoice_line_items_output(
            document_id,
            model_payload,
            evidence_context=evidence_context,
        )
        return finalize(normalized, metadata)
    return finalize(
        model_payload,
        {"mapper": None, "repairs": [], "rejected_fields": []},
    )


def _finalized_output(
    normalized: dict[str, Any],
    metadata: dict[str, Any],
    wrapper_repairs: list[str],
    evidence_context: EvidenceContext | None,
    *,
    model_output_schema_name: str | None,
    semantic_type: str | None,
    target_schema: str | None,
    resolved_document_type: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return finalized_region_output(
        normalized,
        metadata,
        wrapper_repairs,
        evidence_context,
        model_output_schema_name=model_output_schema_name,
        semantic_type=semantic_type,
        target_schema=target_schema,
        resolved_document_type=resolved_document_type,
    )


def invoice_line_item_dicts_from_payload(
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None = None,
) -> list[dict[str, Any]]:
    model_payload, _repairs = _unwrapped_payload(payload)
    records = _invoice_line_item_records(model_payload)
    if records:
        return _canonical_invoice_line_items(records, evidence_context=evidence_context)
    return _flat_invoice_line_items(model_payload, evidence_context=evidence_context)


def invoice_payment_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_invoice = payload.get("invoice")
    invoice: dict[str, Any] = raw_invoice if isinstance(raw_invoice, dict) else {}
    raw_totals = payload.get("totals")
    totals: dict[str, Any] = raw_totals if isinstance(raw_totals, dict) else {}
    raw_metadata = payload.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    raw_payment_summary = metadata.get("payment_summary")
    payment_summary: dict[str, Any] = (
        raw_payment_summary if isinstance(raw_payment_summary, dict) else {}
    )
    payment = _first_payment(payload)
    amount = _money(payment.get("amount") or payload.get("amount") or totals.get("amount_paid"))
    summary = {
        key: value
        for key, value in {
            "card_number": (
                payment.get("card_number")
                or payload.get("card_number")
                or payment_summary.get("card_number")
            ),
            "merchant_id": (
                payment.get("merchant_id")
                or payload.get("merchant_id")
                or payment_summary.get("merchant_id")
            ),
            "terminal_id": (
                payment.get("terminal_id")
                or payload.get("terminal_id")
                or payment_summary.get("terminal_id")
            ),
            "auth_code": (
                payment.get("auth_code")
                or payload.get("auth_code")
                or payment_summary.get("auth_code")
            ),
            "auth_mode": (
                payment.get("auth_mode")
                or payload.get("auth_mode")
                or payment_summary.get("auth_mode")
            ),
            "application_name": payment.get("application_name") or payload.get("application_name"),
        }.items()
        if value not in (None, "")
    }
    return {
        "invoice_number": (
            payload.get("invoice_no")
            or payload.get("invoice_number")
            or invoice.get("invoice_number")
        ),
        "amount_paid": amount,
        "payment_summary": summary,
    }


def _invoice_line_items_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    line_items = invoice_line_item_dicts_from_payload(
        payload,
        evidence_context=evidence_context,
    )
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
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    service_lines = payload.get("service_lines") or []
    if isinstance(service_lines, list):
        service_lines = [
            _with_evidence_context(item, evidence_context)
            for item in service_lines
            if isinstance(item, dict)
        ]
    return (
        {
            "schema_name": "medical_eob",
            "schema_version": "v1",
            "document_id": str(document_id),
            "service_lines": service_lines,
            "confidence": confidence,
            "created_at": datetime.now(UTC).isoformat(),
        },
        {
            "mapper": "granite_medical_service_lines.v1",
            "repairs": ["mapped_model_output_to_canonical_medical_service_lines"],
            "rejected_fields": _rejected_fields(payload, {"service_lines", "confidence"}),
        },
    )


def _receipt_line_items_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    line_items = _canonical_receipt_line_items(
        _invoice_line_item_records(payload),
        evidence_context=evidence_context,
    )
    if not line_items:
        line_items = _canonical_receipt_line_items(
            payload.get("line_items") or [],
            evidence_context=evidence_context,
        )
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    transaction: dict[str, Any] = {}
    raw_totals = payload.get("totals")
    totals: dict[str, Any] = raw_totals if isinstance(raw_totals, dict) else {}
    for source_key, target_key in (
        ("subtotal", "subtotal"),
        ("tax", "tax"),
        ("tax_total", "tax"),
        ("total", "total"),
    ):
        amount = _money(totals.get(source_key) or payload.get(source_key))
        if amount:
            transaction[target_key] = amount
    normalized: dict[str, Any] = {
        "schema_name": "receipt",
        "schema_version": "v1",
        "document_id": str(document_id),
        "merchant": _receipt_merchant(payload, evidence_context=evidence_context),
        "transaction": transaction,
        "line_items": line_items,
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return normalized, {
        "mapper": "granite_receipt_line_items.v1",
        "repairs": ["mapped_model_output_to_canonical_receipt_line_items"],
        "rejected_fields": _rejected_fields(
            payload,
            {"line_items", "totals", "confidence", "merchant_name", "order_number", "order_date"},
        ),
    }


def _service_record_line_items_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = _invoice_line_item_records(payload)
    line_items = _canonical_receipt_line_items(records, evidence_context=evidence_context)
    repairs = ["mapped_model_output_to_canonical_service_record_line_items"]
    if not line_items:
        line_items = _service_record_flat_line_items(payload, evidence_context=evidence_context)
        repairs.append("mapped_flat_service_record_fields_to_line_items")
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    transaction: dict[str, Any] = {}
    raw_totals = payload.get("totals")
    totals: dict[str, Any] = raw_totals if isinstance(raw_totals, dict) else {}
    for source_key, target_key in (
        ("subtotal", "subtotal"),
        ("tax", "tax"),
        ("tax_total", "tax"),
        ("total", "total"),
    ):
        amount = _money(totals.get(source_key) or payload.get(source_key))
        if amount:
            transaction[target_key] = amount
    normalized: dict[str, Any] = {
        "schema_name": "receipt",
        "schema_version": "v1",
        "document_id": str(document_id),
        "merchant": _receipt_merchant(payload, evidence_context=evidence_context),
        "transaction": transaction,
        "line_items": line_items,
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
        "metadata": {"document_family": "service_record"},
    }
    return normalized, {
        "mapper": "granite_service_record_line_items.v1",
        "repairs": repairs,
        "rejected_fields": _rejected_fields(
            payload,
            {
                "line_items",
                "service_description",
                "labor_operation",
                "part_number",
                "parts",
                "quantity",
                "unit",
                "unit_price",
                "line_total",
                "amount",
                "totals",
                "subtotal",
                "tax",
                "tax_total",
                "total",
                "confidence",
                "merchant",
                "merchant_name",
            },
        ),
    }


def _receipt_payment_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    transaction: dict[str, Any] = {}
    for source_key, target_key in (
        ("transaction_date", "date_local"),
        ("subtotal", "subtotal"),
        ("tax", "tax"),
        ("tip", "tip"),
        ("total", "total"),
    ):
        value = payload.get(source_key)
        if target_key in {"subtotal", "tax", "tip", "total"}:
            amount = _money(value)
            if amount:
                transaction[target_key] = amount
        elif value not in (None, ""):
            transaction[target_key] = str(value)
    normalized: dict[str, Any] = {
        "schema_name": "receipt",
        "schema_version": "v1",
        "document_id": str(document_id),
        "merchant": _receipt_merchant(payload, evidence_context=evidence_context),
        "transaction": transaction,
        "line_items": [],
        "confidence": confidence,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if payload.get("payment_method"):
        normalized["metadata"] = {"payment_method": str(payload["payment_method"])}
    return normalized, {
        "mapper": "granite_receipt_payment_summary.v1",
        "repairs": ["mapped_model_output_to_canonical_receipt_payment_summary"],
        "rejected_fields": _rejected_fields(
            payload,
            {
                "merchant_name",
                "transaction_date",
                "subtotal",
                "tax",
                "tip",
                "total",
                "payment_method",
                "confidence",
            },
        ),
    }


def _document_observation_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    model_output_schema_name: str | None,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repairs: list[str] = []
    observations: list[dict[str, Any]] = []
    if _looks_like_schema_echo(payload):
        repairs.append("schema_echo_rejected")
    else:
        observations = _observations_from_model_payload(
            payload,
            model_output_schema_name,
            evidence_context=evidence_context,
        )
        if "fields" in payload:
            repairs.append("mapped_fields_array_to_observations")
        else:
            repairs.append("mapped_flat_fields_to_observations")
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    return (
        {
            "schema_name": "document_observation",
            "schema_version": "v1",
            "document_id": str(document_id),
            "observations": observations,
            "confidence": confidence,
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {"model_output_schema_name": model_output_schema_name},
        },
        {
            "mapper": model_output_schema_name or "granite_generic_kvp.v1",
            "repairs": repairs,
            "rejected_fields": _rejected_fields(
                payload,
                {"fields", "confidence", *{item["field_name"] for item in observations}},
            ),
        },
    )


def observation_dicts_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return []
    return [dict(item) for item in observations if isinstance(item, dict)]


def _canonical_invoice_line_items(
    items: list[Any],
    *,
    evidence_context: EvidenceContext | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = _line_item_description(item)
        if not description:
            continue
        if _is_non_line_item_heading(item, description):
            continue
        amount = _line_item_amount(item)
        service_date = item.get("service_date") or item.get("date")
        normalized_item = {
            "ordinal": int(item.get("ordinal") or len(normalized) + 1),
            "description": description,
            **({"service_date": service_date} if service_date else {}),
            **({"quantity": _number(item.get("quantity"))} if item.get("quantity") else {}),
            **({"unit": item.get("unit")} if item.get("unit") else {}),
            **({"unit_price": _money(item.get("unit_price"))} if item.get("unit_price") else {}),
            **({"amount": amount} if amount else {}),
            **(
                {"gl_hint": item.get("gl_hint") or item.get("category_hint")}
                if (item.get("gl_hint") or item.get("category_hint"))
                else {}
            ),
            "evidence": [_evidence(_line_item_source_text(item, description), evidence_context)],
        }
        normalized.append(normalized_item)
    return normalized


def _canonical_receipt_line_items(
    items: Any,
    *,
    evidence_context: EvidenceContext | None,
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = _line_item_description(item)
        if not description:
            continue
        amount = _line_item_amount(item)
        normalized_item = {
            "ordinal": int(item.get("ordinal") or len(normalized) + 1),
            "description": description,
            **({"quantity": _number(item.get("quantity"))} if item.get("quantity") else {}),
            **({"unit_price": _money(item.get("unit_price"))} if item.get("unit_price") else {}),
            **({"amount": amount} if amount else {}),
            **({"sku": item.get("sku")} if item.get("sku") else {}),
            "evidence": [_evidence(_line_item_source_text(item, description), evidence_context)],
        }
        normalized.append(normalized_item)
    return normalized


def _flat_invoice_line_items(
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> list[dict[str, Any]]:
    service_descriptions = _string_list(payload.get("service_description"))
    parts = _string_list(payload.get("parts"))
    labor_costs = _string_list(payload.get("labor_cost"))
    parts_costs = _string_list(payload.get("parts_cost"))
    items: list[dict[str, Any]] = []
    for index, description in enumerate(service_descriptions):
        amount = _money(labor_costs[index] if index < len(labor_costs) else None)
        items.append(
            _line_item(
                len(items) + 1,
                description,
                amount,
                "service",
                evidence_context=evidence_context,
            )
        )
    for index, description in enumerate(parts):
        amount = _money(parts_costs[index] if index < len(parts_costs) else None)
        items.append(
            _line_item(
                len(items) + 1,
                description,
                amount,
                "part",
                evidence_context=evidence_context,
            )
        )
    return items


def _service_record_flat_line_items(
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> list[dict[str, Any]]:
    service_descriptions = _string_list(payload.get("service_description"))
    labor_operations = _string_list(payload.get("labor_operation"))
    part_numbers = _string_list(payload.get("part_number") or payload.get("parts"))
    quantities = _string_list(payload.get("quantity"))
    unit_prices = _string_list(payload.get("unit_price"))
    line_totals = _string_list(payload.get("line_total") or payload.get("amount"))
    units = _string_list(payload.get("unit"))
    items: list[dict[str, Any]] = []
    for index, description in enumerate(service_descriptions):
        items.append(
            _service_record_line_item(
                ordinal=len(items) + 1,
                description=description,
                category_hint="service",
                quantity=quantities[index] if index < len(quantities) else None,
                unit=units[index] if index < len(units) else None,
                unit_price=unit_prices[index] if index < len(unit_prices) else None,
                amount=line_totals[index] if index < len(line_totals) else None,
                source_text=_join_source_text(
                    description,
                    labor_operation=(
                        labor_operations[index] if index < len(labor_operations) else None
                    ),
                ),
                evidence_context=evidence_context,
            )
        )
    for index, part_number in enumerate(part_numbers):
        amount_index = len(service_descriptions) + index
        items.append(
            _service_record_line_item(
                ordinal=len(items) + 1,
                description=part_number,
                category_hint="part",
                quantity=quantities[index] if index < len(quantities) else None,
                unit=units[index] if index < len(units) else None,
                unit_price=unit_prices[index] if index < len(unit_prices) else None,
                amount=(
                    line_totals[amount_index]
                    if amount_index < len(line_totals)
                    else (line_totals[index] if index < len(line_totals) else None)
                ),
                source_text=part_number,
                evidence_context=evidence_context,
            )
        )
    return [item for item in items if item["description"]]


def _service_record_line_item(
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
) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "ordinal": ordinal,
        "description": description,
        "category_hint": category_hint,
        "evidence": [_evidence(source_text, evidence_context)],
    }
    parsed_quantity = _number(quantity)
    parsed_unit_price = _money(unit_price)
    parsed_amount = _money(amount)
    if parsed_quantity is not None:
        normalized["quantity"] = parsed_quantity
    if unit not in (None, ""):
        normalized["unit"] = str(unit)
    if parsed_unit_price is not None:
        normalized["unit_price"] = parsed_unit_price
    if parsed_amount is not None:
        normalized["amount"] = parsed_amount
    return normalized


def _join_source_text(description: str, **parts: Any) -> str:
    values = [description]
    for key, value in parts.items():
        if value not in (None, ""):
            values.append(f"{key}: {value}")
    return " | ".join(values)


def _line_item(
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


def _invoice_line_item_records(payload: dict[str, Any]) -> list[Any]:
    if isinstance(payload.get("line_items"), list):
        return list(payload["line_items"])
    if isinstance(payload.get("invoice_line_items"), list):
        return list(payload["invoice_line_items"])
    data = payload.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("line_items"), list):
            return list(data["line_items"])
        if isinstance(data.get("invoice_line_items"), list):
            return list(data["invoice_line_items"])
    return []


def _receipt_merchant(
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    merchant_name = payload.get("merchant_name") or payload.get("merchant")
    if isinstance(merchant_name, dict):
        return merchant_name
    if merchant_name:
        return {
            "display_name": str(merchant_name),
            "evidence": [_evidence(merchant_name, evidence_context)],
        }
    return {}


def _line_item_description(item: dict[str, Any]) -> str | None:
    for key in ("description", "service_description", "service_type", "line_description"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _line_item_amount(item: dict[str, Any]) -> dict[str, Any] | None:
    for key in (
        "amount",
        "total_due",
        "service_cost",
        "subtotal",
        "net_amount",
        "line_total",
        "labor",
        "parts_cost",
    ):
        amount = _money(item.get(key))
        if amount is not None:
            return amount
    return None


def _is_non_line_item_heading(item: dict[str, Any], description: str) -> bool:
    normalized_description = description.strip().lower()
    category = item.get("category_hint") or item.get("gl_hint")
    normalized_category = str(category).strip().lower() if category else ""
    return (
        normalized_description in _NON_LINE_ITEM_HEADINGS
        or normalized_category in _NON_LINE_ITEM_HEADINGS
    )


def _line_item_source_text(item: dict[str, Any], description: str) -> str:
    parts = [description]
    for key in ("parts", "service_notes", "service_provider", "service_location"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{key}: {value.strip()}")
    return " | ".join(parts)


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


def _healthcare_coverage_decision_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for item in payload.get("facts") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if not name or _should_drop_observation(name, value):
            continue
        observations.append(
            _observation(
                field_name=str(name),
                value=value,
                family="granite_healthcare_coverage_decision.v1",
                confidence=_number(item.get("confidence")),
                source_text=item.get("source_text") or value,
                evidence_context=evidence_context,
            )
        )

    for index, item in enumerate(payload.get("contacts") or [], start=1):
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key in {"confidence", "source_text"} or _should_drop_observation(key, value):
                continue
            observations.append(
                _observation(
                    field_name=f"contact_{index}.{key}",
                    value=value,
                    family="granite_healthcare_coverage_decision.v1",
                    confidence=_number(item.get("confidence")),
                    source_text=item.get("source_text") or value,
                    evidence_context=evidence_context,
                )
            )

    for index, item in enumerate(payload.get("service_lines") or [], start=1):
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key in {"confidence", "source_text"} or _should_drop_observation(key, value):
                continue
            observations.append(
                _observation(
                    field_name=f"service_line_{index}.{key}",
                    value=value,
                    family="granite_healthcare_coverage_decision.v1",
                    confidence=_number(item.get("confidence")),
                    source_text=item.get("source_text") or value,
                    evidence_context=evidence_context,
                )
            )

    return (
        {
            "schema_name": "document_observation",
            "schema_version": "v1",
            "document_id": str(document_id),
            "observations": observations,
            "confidence": (
                payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
            ),
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {"model_output_schema_name": "granite_healthcare_coverage_decision.v1"},
        },
        {
            "mapper": "granite_healthcare_coverage_decision.v1",
            "repairs": ["mapped_healthcare_coverage_decision_to_observations"],
            "rejected_fields": _rejected_fields(
                payload,
                {"facts", "contacts", "service_lines", "warnings", "confidence"},
            ),
        },
    )


def _looks_like_schema_echo(payload: dict[str, Any]) -> bool:
    if "$schema" in payload or "$defs" in payload:
        return True
    if "properties" in payload and ("type" in payload or "required" in payload):
        schema_keys = {
            "$schema",
            "$defs",
            "type",
            "properties",
            "required",
            "additionalProperties",
            "title",
            "description",
            "items",
        }
        return set(payload).issubset(schema_keys)
    return False


def _observations_from_model_payload(
    payload: dict[str, Any],
    model_output_schema_name: str | None,
    *,
    evidence_context: EvidenceContext | None,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    fields = payload.get("fields")
    if isinstance(fields, list):
        for item in fields:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if not name or _should_drop_observation(name, value):
                continue
            observations.append(
                _observation(
                    field_name=str(name),
                    value=value,
                    family=model_output_schema_name,
                    confidence=_number(item.get("confidence")),
                    source_text=item.get("source_text"),
                    evidence_context=evidence_context,
                )
            )
        return observations
    for key, value in payload.items():
        if _should_drop_observation(key, value):
            continue
        observations.append(
            _observation(
                field_name=str(key),
                value=value,
                family=model_output_schema_name,
                confidence=None,
                source_text=value,
                evidence_context=evidence_context,
            )
        )
    return observations


def _observation(
    *,
    field_name: str,
    value: Any,
    family: str | None,
    confidence: float | None,
    source_text: object,
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    bounded_source_text = _bounded_text(source_text, max_length=500)
    return {
        "family": family,
        "field_name": field_name,
        "value": value,
        "value_type": _value_type(value),
        "source_text": bounded_source_text,
        "confidence": confidence,
        "evidence": [
            _evidence(
                bounded_source_text if bounded_source_text else field_name,
                evidence_context,
            )
        ],
    }


def _should_drop_observation(key: object, value: object) -> bool:
    normalized_key = str(key or "").strip().lower()
    if normalized_key in _DROP_FLAT_OBSERVATION_KEYS:
        return True
    if value in (None, ""):
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return _contains_instruction_echo(key) or _contains_instruction_echo(value)


def _contains_instruction_echo(value: object) -> bool:
    if isinstance(value, str):
        text = value.lower()
        return any(phrase in text for phrase in _ECHO_PHRASES)
    if isinstance(value, dict):
        return any(
            _contains_instruction_echo(key) or _contains_instruction_echo(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_instruction_echo(item) for item in value)
    return False


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, dict | list):
        return "json"
    return "string"


def _unwrapped_payload(payload: Any) -> tuple[dict[str, Any], list[str]]:
    repairs: list[str] = []
    if not isinstance(payload, dict):
        repairs.append(f"coerced_{type(payload).__name__}_payload_to_observation_shell")
        if isinstance(payload, list):
            fields = [
                {"name": f"item_{index + 1}", "value": item} for index, item in enumerate(payload)
            ]
            return {"fields": fields}, repairs
        if payload is None:
            return {}, repairs
        return {"fields": [{"name": "raw_text", "value": str(payload)}]}, repairs
    normalized = payload.get("normalized")
    if isinstance(normalized, dict):
        repairs.append("unwrapped_normalized_payload")
        return _merged_wrapper_payload(payload, normalized, wrapper_key="normalized"), repairs
    data = payload.get("data")
    if isinstance(data, dict):
        repairs.append("unwrapped_data_payload")
        return _merged_wrapper_payload(payload, data, wrapper_key="data"), repairs
    return payload, repairs


def _merged_wrapper_payload(
    payload: dict[str, Any],
    wrapped: dict[str, Any],
    *,
    wrapper_key: str,
) -> dict[str, Any]:
    merged = {key: value for key, value in payload.items() if key != wrapper_key}
    merged.update(wrapped)
    return merged


def _bounded_text(value: object, *, max_length: int) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) <= max_length:
        return text
    return text[:max_length]


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


def _with_evidence_context(
    item: dict[str, Any],
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    copied = dict(item)
    evidence = copied.get("evidence")
    if isinstance(evidence, list) and evidence:
        copied["evidence"] = [
            _merge_evidence_context(entry, evidence_context)
            for entry in evidence
            if isinstance(entry, dict)
        ]
    else:
        source_text = (
            copied.get("source_text")
            or copied.get("service_description")
            or copied.get("description")
            or copied.get("procedure_code")
            or copied.get("ordinal")
        )
        copied["evidence"] = [_evidence(source_text, evidence_context)]
    return copied


def _merge_evidence_context(
    item: dict[str, Any],
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    if evidence_context is None:
        return dict(item)
    grounded = _evidence(item.get("source_text") or "", evidence_context)
    return {**item, **{key: value for key, value in grounded.items() if key != "source_text"}}


def _rejected_fields(payload: dict[str, Any], accepted: set[str]) -> list[str]:
    return sorted(key for key in payload if key not in accepted)
