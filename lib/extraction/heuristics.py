from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from lib.extraction.evidence import EvidenceResolver
from lib.extraction.models import ExtractionSourceDocument

MONEY_PATTERN = re.compile(r"(?<!\w)\$?\s*([0-9]{1,6}(?:,[0-9]{3})*(?:\.[0-9]{2})?)")
DATE_PATTERNS = (
    re.compile(r"\b(20[0-9]{2}-[01][0-9]-[0-3][0-9])\b"),
    re.compile(r"\b([01]?[0-9]/[0-3]?[0-9]/20[0-9]{2})\b"),
)


def receipt_payload(source: ExtractionSourceDocument) -> dict[str, Any]:
    resolver = EvidenceResolver(source)
    text = source.full_text
    merchant = _labeled_value(text, ("merchant", "store")) or _first_meaningful_line(text)
    transaction_date = _find_date(_labeled_value(text, ("date", "transaction date")) or text)
    subtotal = _money_after(text, ("subtotal",))
    tax = _money_after(text, ("tax", "sales tax"))
    tip = _money_after(text, ("tip",))
    discount = _money_after(text, ("discount",))
    total = _money_after(text, ("total", "amount paid", "grand total"))
    line_items = _line_items(text, resolver, "receipt_item")

    return _without_none(
        {
            "schema_name": "receipt",
            "schema_version": "v1",
            "document_id": str(source.document_id),
            "merchant": {
                "display_name": merchant or "Unknown merchant",
                "party_type": "merchant",
                "evidence": resolver.for_value(merchant or source.title),
            },
            "transaction": _without_none(
                {
                    "date_local": transaction_date,
                    "subtotal": _money(subtotal),
                    "tax": _money(tax),
                    "tip": _money(tip),
                    "discount_total": _money(discount),
                    "total": _money(total),
                    "evidence": resolver.for_value(total or transaction_date or merchant),
                }
            ),
            "line_items": line_items,
            "confidence": {"overall": 0.84, "schema_fit": 0.82},
            "validation": {"needs_review": False, "checks": []},
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {"extractor": "docling_heuristic_v1"},
        }
    )


def invoice_payload(source: ExtractionSourceDocument) -> dict[str, Any]:
    resolver = EvidenceResolver(source)
    text = source.full_text
    seller = _labeled_value(text, ("seller", "vendor", "from")) or _first_meaningful_line(text)
    buyer = _labeled_value(text, ("buyer", "bill to"))
    invoice_number = _labeled_value(text, ("invoice number", "invoice #", "invoice no"))
    issued_on = _find_date(_labeled_value(text, ("issue date", "issued on", "date")) or "")
    due_on = _find_date(_labeled_value(text, ("due date", "due on")) or "")
    subtotal = _money_after(text, ("subtotal",))
    tax = _money_after(text, ("tax",))
    discount = _money_after(text, ("discount",))
    shipping = _money_after(text, ("shipping",))
    paid = _money_after(text, ("amount paid", "paid"))
    balance = _money_after(text, ("balance due", "amount due"))
    total = _money_after(text, ("invoice total", "total", "amount due"))
    line_items = _line_items(text, resolver, "invoice_item")

    payload: dict[str, Any] = {
        "schema_name": "invoice",
        "schema_version": "v1",
        "document_id": str(source.document_id),
        "seller": {
            "display_name": seller or "Unknown seller",
            "party_type": "vendor",
            "evidence": resolver.for_value(seller or source.title),
        },
        "invoice": _without_none(
            {
                "invoice_number": invoice_number or _fallback_identifier(source.document_id),
                "issued_on": issued_on,
                "due_on": due_on,
                "evidence": resolver.for_value(invoice_number or due_on or seller),
            }
        ),
        "line_items": line_items,
        "totals": _without_none(
            {
                "subtotal": _money(subtotal),
                "tax_total": _money(tax),
                "discount_total": _money(discount),
                "shipping_total": _money(shipping),
                "total": _money(total or balance),
                "amount_paid": _money(paid),
                "balance_due": _money(balance),
                "evidence": resolver.for_value(total or balance or seller),
            }
        ),
        "confidence": {"overall": 0.83, "schema_fit": 0.82},
        "validation": {"needs_review": False, "checks": []},
        "created_at": datetime.now(UTC).isoformat(),
        "metadata": {"extractor": "docling_heuristic_v1"},
    }
    if buyer:
        payload["buyer"] = {
            "display_name": buyer,
            "party_type": "company",
            "evidence": resolver.for_value(buyer),
        }
    return payload


def medical_eob_payload(source: ExtractionSourceDocument) -> dict[str, Any]:
    resolver = EvidenceResolver(source)
    text = source.full_text
    payer = _labeled_value(text, ("payer", "insurer", "insurance")) or _first_meaningful_line(text)
    patient = _labeled_value(text, ("patient", "member"))
    provider = _labeled_value(text, ("provider",))
    claim_number = _labeled_value(text, ("claim number", "claim #", "claim no"))
    billed = _money_after(text, ("total billed", "billed amount"))
    allowed = _money_after(text, ("total allowed", "allowed amount"))
    plan_paid = _money_after(text, ("plan paid", "insurance paid", "paid by plan"))
    patient_resp = _money_after(
        text, ("patient responsibility", "you owe", "member responsibility")
    )
    service_lines = _eob_service_lines(text, resolver)

    payload: dict[str, Any] = {
        "schema_name": "medical_eob",
        "schema_version": "v1",
        "document_id": str(source.document_id),
        "payer": {
            "display_name": payer or "Unknown payer",
            "party_type": "payer",
            "evidence": resolver.for_value(payer or source.title),
        },
        "patient": {
            "display_name": patient or "Unknown patient",
            "party_type": "person",
            "evidence": resolver.for_value(patient or "patient"),
        },
        "claim": _without_none(
            {
                "claim_number": claim_number,
                "evidence": resolver.for_value(claim_number or payer),
            }
        ),
        "service_lines": service_lines,
        "financial_summary": _without_none(
            {
                "total_billed": _money(billed),
                "total_allowed": _money(allowed),
                "total_plan_paid": _money(plan_paid),
                "total_patient_responsibility": _money(patient_resp),
                "evidence": resolver.for_value(patient_resp or plan_paid or payer),
            }
        ),
        "confidence": {"overall": 0.78, "schema_fit": 0.77},
        "validation": {"needs_review": True, "checks": []},
        "created_at": datetime.now(UTC).isoformat(),
        "metadata": {"extractor": "docling_heuristic_v1", "policy": "medical_review_required"},
    }
    if provider:
        payload["provider"] = {
            "display_name": provider,
            "party_type": "provider",
            "evidence": resolver.for_value(provider),
        }
    return payload


def classify_text_signals(
    source: ExtractionSourceDocument,
) -> tuple[str, str | None, list[str], float]:
    text = f"{source.original_filename or ''}\n{source.title}\n{source.full_text}".lower()
    if any(
        token in text for token in ("explanation of benefits", " eob", "patient responsibility")
    ):
        return "medical_eob", "explanation_of_benefits", ["eob keywords", "medical amounts"], 0.86
    if any(token in text for token in ("invoice", "balance due", "invoice number", "bill to")):
        return "invoice", None, ["invoice keywords", "billing fields"], 0.85
    if any(token in text for token in ("receipt", "subtotal", "sales tax", "transaction date")):
        return "receipt", None, ["receipt keywords", "retail totals"], 0.84
    if source.metadata.get("phase3", {}).get("parseStatus") != "succeeded":
        return "generic", None, ["no canonical parse success signal"], 0.35
    return "generic", None, ["no target schema keywords"], 0.5


def _money(amount: Decimal | None) -> dict[str, Any] | None:
    if amount is None:
        return None
    return {"amount": float(amount), "currency": "USD"}


def _money_after(text: str, labels: tuple[str, ...]) -> Decimal | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:#]?\s*\$?\s*([0-9,]+\.[0-9]{{2}})", text, re.I)
        if match:
            return _decimal(match.group(1))
    return None


def _find_date(text: str) -> str | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = match.group(1)
        if "-" in raw:
            return raw
        month, day, year = raw.split("/")
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return None


def _labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"^{re.escape(label)}\s*[:#]\s*(.+)$", text, re.I | re.M)
        if match:
            return match.group(1).strip()
    return None


def _first_meaningful_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip(" -\t")
        if len(stripped) >= 3 and not MONEY_PATTERN.search(stripped):
            return stripped[:120]
    return None


def _line_items(
    text: str,
    resolver: EvidenceResolver,
    item_type: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = re.match(
            r"^\s*(?:item|line)\s*[:#-]?\s*(.+?)\s+\$?([0-9,]+\.[0-9]{2})\s*$", line, re.I
        )
        if not match:
            continue
        amount = _decimal(match.group(2))
        if amount is None:
            continue
        items.append(
            {
                "ordinal": len(items) + 1,
                "description": match.group(1).strip()[:180],
                "amount": _money(amount),
                "evidence": resolver.for_value(line.strip()),
                "category_hint": item_type,
            }
        )
    return items


def _eob_service_lines(text: str, resolver: EvidenceResolver) -> list[dict[str, Any]]:
    lines = _line_items(text, resolver, "service_line")
    if lines:
        return [
            {
                "ordinal": item["ordinal"],
                "service_description": item["description"],
                "billed_amount": item["amount"],
                "evidence": item["evidence"],
            }
            for item in lines
        ]
    description = _labeled_value(text, ("service", "service description"))
    if not description:
        return []
    return [
        {
            "ordinal": 1,
            "service_description": description,
            "patient_responsibility": _money(
                _money_after(text, ("patient responsibility", "you owe")) or Decimal("0.00")
            ),
            "evidence": resolver.for_value(description),
        }
    ]


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _fallback_identifier(document_id: UUID) -> str:
    return f"unknown-{str(document_id)[:8]}"


def _without_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
