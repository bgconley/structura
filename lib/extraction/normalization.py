from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.models import CandidateFact, Evidence, LineItemCandidateFact, ValidationReport

AUTHORITY_WEIGHTS = {
    "docling": 0.62,
    "granite_vision_3b": 0.82,
    "qwen3_vl_8b": 0.78,
    "qwen3_vl_4b": 0.72,
    "validator": 0.9,
    "human": 1.0,
    "system": 0.55,
}


def field_candidates_from_extraction(
    *,
    document_id: UUID,
    schema_name: str,
    payload: dict[str, Any],
    validation: ValidationReport,
    source_engine: str,
) -> list[CandidateFact]:
    del document_id
    evidence_fallback = _first_evidence(payload)
    confidence = _overall_confidence(payload)
    status = _candidate_status(validation, evidence_fallback)
    if schema_name == "receipt":
        return _receipt_candidates(payload, confidence, source_engine, validation, status)
    if schema_name == "invoice":
        return _invoice_candidates(payload, confidence, source_engine, validation, status)
    if schema_name == "medical_eob":
        return _eob_candidates(payload, confidence, source_engine, validation, "needs_review")
    return []


def line_item_candidates_from_extraction(
    *,
    schema_name: str,
    payload: dict[str, Any],
    validation: ValidationReport,
    source_engine: str,
) -> list[LineItemCandidateFact]:
    confidence = _overall_confidence(payload)
    status = _candidate_status(validation, _first_evidence(payload))
    if schema_name == "receipt":
        return _line_items(
            payload.get("line_items"), "receipt_item", source_engine, confidence, status
        )
    if schema_name == "invoice":
        return _line_items(
            payload.get("line_items"), "invoice_item", source_engine, confidence, status
        )
    if schema_name == "medical_eob":
        return _eob_line_items(
            payload.get("service_lines"), source_engine, confidence, "needs_review"
        )
    return []


def _receipt_candidates(
    payload: dict[str, Any],
    confidence: float,
    source_engine: str,
    validation: ValidationReport,
    status: str,
) -> list[CandidateFact]:
    merchant = payload.get("merchant") or {}
    transaction = payload.get("transaction") or {}
    return [
        *_candidate(
            "receipt.merchant.display_name",
            "string",
            merchant.get("display_name"),
            merchant,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_candidate(
            "receipt.transaction.date_local",
            "date",
            transaction.get("date_local"),
            transaction,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "receipt.transaction.subtotal",
            transaction.get("subtotal"),
            transaction,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "receipt.transaction.tax",
            transaction.get("tax"),
            transaction,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "receipt.transaction.total",
            transaction.get("total"),
            transaction,
            confidence,
            source_engine,
            validation,
            status,
        ),
    ]


def _invoice_candidates(
    payload: dict[str, Any],
    confidence: float,
    source_engine: str,
    validation: ValidationReport,
    status: str,
) -> list[CandidateFact]:
    seller = payload.get("seller") or {}
    invoice = payload.get("invoice") or {}
    totals = payload.get("totals") or {}
    return [
        *_candidate(
            "invoice.seller.display_name",
            "string",
            seller.get("display_name"),
            seller,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_candidate(
            "invoice.invoice_number",
            "string",
            invoice.get("invoice_number"),
            invoice,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_candidate(
            "invoice.issue_date",
            "date",
            invoice.get("issued_on"),
            invoice,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_candidate(
            "invoice.due_date",
            "date",
            invoice.get("due_on"),
            invoice,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "invoice.subtotal",
            totals.get("subtotal"),
            totals,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "invoice.tax_total",
            totals.get("tax_total"),
            totals,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "invoice.total_amount",
            totals.get("total"),
            totals,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "invoice.balance_due",
            totals.get("balance_due"),
            totals,
            confidence,
            source_engine,
            validation,
            status,
        ),
    ]


def _eob_candidates(
    payload: dict[str, Any],
    confidence: float,
    source_engine: str,
    validation: ValidationReport,
    status: str,
) -> list[CandidateFact]:
    payer = payload.get("payer") or {}
    patient = payload.get("patient") or {}
    provider = payload.get("provider") or {}
    claim = payload.get("claim") or {}
    summary = payload.get("financial_summary") or {}
    return [
        *_candidate(
            "medical_eob.payer.display_name",
            "string",
            payer.get("display_name"),
            payer,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_candidate(
            "medical_eob.patient.display_name",
            "string",
            patient.get("display_name"),
            patient,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_candidate(
            "medical_eob.provider.display_name",
            "string",
            provider.get("display_name"),
            provider,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_candidate(
            "medical_eob.claim_number",
            "string",
            claim.get("claim_number"),
            claim,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "medical_eob.total_billed",
            summary.get("total_billed"),
            summary,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "medical_eob.total_plan_paid",
            summary.get("total_plan_paid"),
            summary,
            confidence,
            source_engine,
            validation,
            status,
        ),
        *_money_candidate(
            "medical_eob.total_patient_responsibility",
            summary.get("total_patient_responsibility"),
            summary,
            confidence,
            source_engine,
            validation,
            status,
        ),
    ]


def _candidate(
    field_path: str,
    value_type: str,
    value: Any,
    owner: dict[str, Any],
    confidence: float,
    source_engine: str,
    validation: ValidationReport,
    status: str,
) -> list[CandidateFact]:
    if value in (None, ""):
        return []
    evidence = _evidence(owner)
    return [
        CandidateFact(
            field_path=field_path,
            value_type=value_type,
            value=value,
            evidence=evidence,
            confidence=confidence,
            authority_weight=AUTHORITY_WEIGHTS.get(source_engine, 0.5),
            validation=validation.as_json(),
            status=status if has_concrete_evidence(evidence) else "needs_review",
        )
    ]


def _money_candidate(
    field_path: str,
    value: Any,
    owner: dict[str, Any],
    confidence: float,
    source_engine: str,
    validation: ValidationReport,
    status: str,
) -> list[CandidateFact]:
    if not isinstance(value, dict) or value.get("amount") is None:
        return []
    evidence = _evidence(owner)
    return [
        CandidateFact(
            field_path=field_path,
            value_type="money",
            value=value,
            currency=value.get("currency"),
            evidence=evidence,
            confidence=confidence,
            authority_weight=AUTHORITY_WEIGHTS.get(source_engine, 0.5),
            validation=validation.as_json(),
            status=status if has_concrete_evidence(evidence) else "needs_review",
        )
    ]


def _line_items(
    items: Any,
    line_item_type: str,
    source_engine: str,
    confidence: float,
    status: str,
) -> list[LineItemCandidateFact]:
    if not isinstance(items, list):
        return []
    facts: list[LineItemCandidateFact] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("description"):
            continue
        raw_amount = item.get("amount")
        amount = raw_amount if isinstance(raw_amount, dict) else {}
        facts.append(
            LineItemCandidateFact(
                line_item_type=line_item_type,
                ordinal=int(item.get("ordinal") or len(facts) + 1),
                description=str(item["description"]),
                evidence=_evidence(item),
                candidate_group=f"{line_item_type}.default",
                quantity=_number(item.get("quantity")),
                unit=item.get("unit"),
                unit_price=_money_amount(item.get("unit_price")),
                gross_amount=_money_amount(item.get("amount")),
                discount_amount=_money_amount(item.get("discount")),
                net_amount=_money_amount(item.get("amount")),
                currency=amount.get("currency"),
                category_hint=item.get("category_hint"),
                confidence=confidence,
                authority_weight=AUTHORITY_WEIGHTS.get(source_engine, 0.5),
                status=status,
            )
        )
    return facts


def _eob_line_items(
    items: Any,
    source_engine: str,
    confidence: float,
    status: str,
) -> list[LineItemCandidateFact]:
    if not isinstance(items, list):
        return []
    facts: list[LineItemCandidateFact] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("service_description"):
            continue
        facts.append(
            LineItemCandidateFact(
                line_item_type="service_line",
                ordinal=int(item.get("ordinal") or len(facts) + 1),
                description=str(item["service_description"]),
                evidence=_evidence(item),
                candidate_group="medical_eob.service_lines",
                code=item.get("procedure_code"),
                service_date=item.get("service_date"),
                gross_amount=_money_amount(item.get("billed_amount")),
                net_amount=_money_amount(item.get("patient_responsibility")),
                currency=_money_currency(item.get("patient_responsibility")),
                confidence=confidence,
                authority_weight=AUTHORITY_WEIGHTS.get(source_engine, 0.5),
                status=status,
            )
        )
    return facts


def _candidate_status(validation: ValidationReport, evidence: list[dict[str, Any]]) -> str:
    if validation.needs_review or not has_concrete_evidence(evidence):
        return "needs_review"
    return "proposed"


def _first_evidence(payload: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = payload.get("evidence")
    if isinstance(evidence, list):
        return evidence
    for value in payload.values():
        if isinstance(value, dict):
            evidence = value.get("evidence")
            if isinstance(evidence, list):
                return evidence
    return []


def _evidence(owner: dict[str, Any]) -> list[Evidence]:
    evidence = owner.get("evidence")
    return evidence if isinstance(evidence, list) else []


def _overall_confidence(payload: dict[str, Any]) -> float:
    confidence = payload.get("confidence")
    if isinstance(confidence, dict):
        return float(confidence.get("overall") or 0)
    return 0.0


def _money_amount(value: Any) -> float | None:
    if not isinstance(value, dict) or value.get("amount") is None:
        return None
    return float(value["amount"])


def _money_currency(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    currency = value.get("currency")
    return str(currency) if currency else None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
