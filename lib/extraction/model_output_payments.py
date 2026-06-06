from __future__ import annotations

from typing import Any

from lib.extraction.evidence_concretizer import evidence_ref_from_context
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_value_parsing import money_value


def invoice_payment_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payment = first_payment(payload)
    amount = money_value(payment.get("amount") or payload.get("amount"))
    summary = {
        key: value
        for key, value in {
            "card_number": payment.get("card_number"),
            "merchant_id": payment.get("merchant_id"),
            "terminal_id": payment.get("terminal_id"),
            "auth_code": payment.get("auth_code"),
            "auth_mode": payment.get("auth_mode"),
            "application_name": payment.get("application_name"),
        }.items()
        if value not in (None, "")
    }
    return {
        "invoice_number": payload.get("invoice_no"),
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
