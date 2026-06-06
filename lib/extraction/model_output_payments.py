from __future__ import annotations

from typing import Any

from lib.extraction.evidence_concretizer import evidence_ref_from_context
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_value_parsing import money_value, string_values


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
    payment = first_payment(payload)
    amount = money_value(
        payment.get("amount") or payload.get("amount") or totals.get("amount_paid")
    )
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


def invoice_totals(payload: dict[str, Any]) -> dict[str, Any]:
    raw_totals = payload.get("totals")
    totals: dict[str, Any] = raw_totals if isinstance(raw_totals, dict) else {}
    result: dict[str, Any] = {}
    for source_key, target_key in (
        ("subtotal", "subtotal"),
        ("tax_total", "tax_total"),
        ("shipping_total", "shipping_total"),
        ("discount_total", "discount_total"),
        ("total", "total"),
    ):
        amount = money_value(totals.get(source_key))
        if amount:
            result[target_key] = amount
    if not result:
        total_values = string_values(payload.get("total_amount"))
        if total_values:
            amount = money_value(total_values[0])
            if amount:
                result["total"] = amount
    return result


def receipt_merchant(
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


def first_payment(payload: dict[str, Any]) -> dict[str, Any]:
    payments = payload.get("payments")
    if isinstance(payments, list):
        first = next((item for item in payments if isinstance(item, dict)), None)
        if first is not None:
            return first
    return {}


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
