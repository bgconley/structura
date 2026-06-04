from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.extraction.candidate_deduplication import (
    dedupe_line_item_candidates as _dedupe_line_item_candidates,
)
from lib.extraction.candidate_deduplication import (
    dedupe_observation_candidates as _dedupe_observation_candidates,
)
from lib.extraction.candidate_quality import (
    reject_line_item,
    reject_observation,
    reject_scalar_candidate,
)
from lib.extraction.candidate_value_parsing import candidate_status as _candidate_status
from lib.extraction.candidate_value_parsing import confidence_or_none as _confidence_or_none
from lib.extraction.candidate_value_parsing import date_value as _date
from lib.extraction.candidate_value_parsing import (
    empty_observation_value as _empty_observation_value,
)
from lib.extraction.candidate_value_parsing import evidence as _evidence
from lib.extraction.candidate_value_parsing import first_evidence as _first_evidence
from lib.extraction.candidate_value_parsing import (
    grid_only_observation as _grid_only_observation,
)
from lib.extraction.candidate_value_parsing import money_amount as _money_amount
from lib.extraction.candidate_value_parsing import money_currency as _money_currency
from lib.extraction.candidate_value_parsing import number_value as _number
from lib.extraction.candidate_value_parsing import overall_confidence as _overall_confidence
from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.model_output_normalization import (
    invoice_line_item_dicts_from_payload,
    observation_dicts_from_payload,
)
from lib.extraction.models import (
    CandidateFact,
    LineItemCandidateFact,
    ObservationCandidateFact,
    ValidationReport,
)

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
    require_concrete_evidence: bool = False,
) -> list[CandidateFact]:
    del document_id
    evidence_fallback = _first_evidence(payload)
    confidence = _overall_confidence(payload)
    status = _candidate_status(validation, evidence_fallback, source_engine=source_engine)
    if schema_name == "receipt":
        return _receipt_candidates(
            payload, confidence, source_engine, validation, status, require_concrete_evidence
        )
    if schema_name == "invoice":
        return _invoice_candidates(
            payload, confidence, source_engine, validation, status, require_concrete_evidence
        )
    if schema_name == "medical_eob":
        return _eob_candidates(
            payload,
            confidence,
            source_engine,
            validation,
            "needs_review",
            require_concrete_evidence,
        )
    return []


def line_item_candidates_from_extraction(
    *,
    schema_name: str,
    payload: dict[str, Any],
    validation: ValidationReport,
    source_engine: str,
    require_concrete_evidence: bool = False,
) -> list[LineItemCandidateFact]:
    confidence = _overall_confidence(payload)
    status = _candidate_status(validation, _first_evidence(payload), source_engine=source_engine)
    if schema_name == "receipt":
        return _dedupe_line_item_candidates(
            _line_items(
                payload.get("line_items"),
                "receipt_item",
                source_engine,
                confidence,
                status,
                require_concrete_evidence,
            )
        )
    if schema_name == "invoice":
        invoice_items = payload.get("line_items")
        if not isinstance(invoice_items, list) or not invoice_items:
            invoice_items = invoice_line_item_dicts_from_payload(payload)
        return _dedupe_line_item_candidates(
            _line_items(
                invoice_items,
                "invoice_item",
                source_engine,
                confidence,
                status,
                require_concrete_evidence,
            )
        )
    if schema_name == "medical_eob":
        return _dedupe_line_item_candidates(
            _eob_line_items(
                payload.get("service_lines"),
                source_engine,
                confidence,
                "needs_review",
                require_concrete_evidence,
            )
        )
    return []


def observation_candidates_from_extraction(
    *,
    schema_name: str,
    payload: dict[str, Any],
    validation: ValidationReport,
    require_concrete_evidence: bool = False,
) -> list[ObservationCandidateFact]:
    if schema_name != "document_observation":
        return []
    candidates: list[ObservationCandidateFact] = []
    for item in observation_dicts_from_payload(payload):
        field_name = item.get("field_name")
        if not field_name:
            continue
        value = item.get("value")
        rejected, _reason = reject_observation(str(field_name), value)
        if rejected:
            continue
        if _empty_observation_value(value) or _grid_only_observation(field_name, value):
            continue
        evidence = _evidence(item)
        if require_concrete_evidence and not has_concrete_evidence(evidence):
            continue
        candidates.append(
            ObservationCandidateFact(
                observation_family=(
                    str(item["family"]) if item.get("family") not in (None, "") else None
                ),
                field_name=str(field_name),
                value_type=str(item.get("value_type") or "string"),
                value=value,
                evidence=evidence,
                confidence=_confidence_or_none(item.get("confidence")),
                validation=validation.as_json(),
                status="needs_review",
                metadata={
                    "source_text": item.get("source_text"),
                    **(
                        {"semantic_type": str(item["semantic_type"])}
                        if item.get("semantic_type") not in (None, "")
                        else {}
                    ),
                },
            )
        )
    return _dedupe_observation_candidates(candidates)


def _receipt_candidates(
    payload: dict[str, Any],
    confidence: float,
    source_engine: str,
    validation: ValidationReport,
    status: str,
    require_concrete_evidence: bool,
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
            require_concrete_evidence=require_concrete_evidence,
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
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "receipt.transaction.subtotal",
            transaction.get("subtotal"),
            transaction,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "receipt.transaction.tax",
            transaction.get("tax"),
            transaction,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "receipt.transaction.total",
            transaction.get("total"),
            transaction,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
    ]


def _invoice_candidates(
    payload: dict[str, Any],
    confidence: float,
    source_engine: str,
    validation: ValidationReport,
    status: str,
    require_concrete_evidence: bool,
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
            require_concrete_evidence=require_concrete_evidence,
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
            require_concrete_evidence=require_concrete_evidence,
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
            require_concrete_evidence=require_concrete_evidence,
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
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "invoice.subtotal",
            totals.get("subtotal"),
            totals,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "invoice.tax_total",
            totals.get("tax_total"),
            totals,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "invoice.total_amount",
            totals.get("total"),
            totals,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "invoice.balance_due",
            totals.get("balance_due"),
            totals,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
    ]


def _eob_candidates(
    payload: dict[str, Any],
    confidence: float,
    source_engine: str,
    validation: ValidationReport,
    status: str,
    require_concrete_evidence: bool,
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
            require_concrete_evidence=require_concrete_evidence,
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
            require_concrete_evidence=require_concrete_evidence,
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
            require_concrete_evidence=require_concrete_evidence,
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
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "medical_eob.total_billed",
            summary.get("total_billed"),
            summary,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "medical_eob.total_plan_paid",
            summary.get("total_plan_paid"),
            summary,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
        ),
        *_money_candidate(
            "medical_eob.total_patient_responsibility",
            summary.get("total_patient_responsibility"),
            summary,
            confidence,
            source_engine,
            validation,
            status,
            require_concrete_evidence=require_concrete_evidence,
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
    *,
    require_concrete_evidence: bool = False,
) -> list[CandidateFact]:
    if value in (None, ""):
        return []
    if value_type == "date":
        value = _date(value)
        if value is None:
            return []
    rejected, _reason = reject_scalar_candidate(value)
    if rejected:
        return []
    evidence = _evidence(owner)
    if require_concrete_evidence and not has_concrete_evidence(evidence):
        return []
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
    *,
    require_concrete_evidence: bool = False,
) -> list[CandidateFact]:
    if not isinstance(value, dict) or value.get("amount") is None:
        return []
    evidence = _evidence(owner)
    if not evidence:
        evidence = _evidence(value)
    if require_concrete_evidence and not has_concrete_evidence(evidence):
        return []
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
    require_concrete_evidence: bool = False,
) -> list[LineItemCandidateFact]:
    if not isinstance(items, list):
        return []
    facts: list[LineItemCandidateFact] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("description"):
            continue
        rejected, _reason = reject_line_item(item)
        if rejected:
            continue
        evidence = _evidence(item)
        if require_concrete_evidence and not has_concrete_evidence(evidence):
            continue
        raw_amount = item.get("amount")
        amount = raw_amount if isinstance(raw_amount, dict) else {}
        facts.append(
            LineItemCandidateFact(
                line_item_type=line_item_type,
                ordinal=int(item.get("ordinal") or len(facts) + 1),
                description=str(item["description"]),
                evidence=evidence,
                candidate_group=f"{line_item_type}.default",
                service_date=_date(item.get("service_date")),
                quantity=_number(item.get("quantity")),
                unit=item.get("unit"),
                unit_price=_money_amount(item.get("unit_price")),
                gross_amount=_money_amount(item.get("amount")),
                discount_amount=_money_amount(item.get("discount")),
                net_amount=_money_amount(item.get("amount")),
                currency=amount.get("currency"),
                category_hint=item.get("category_hint") or item.get("gl_hint"),
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
    require_concrete_evidence: bool = False,
) -> list[LineItemCandidateFact]:
    if not isinstance(items, list):
        return []
    facts: list[LineItemCandidateFact] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("service_description"):
            continue
        rejected, _reason = reject_line_item(item)
        if rejected:
            continue
        evidence = _evidence(item)
        if require_concrete_evidence and not has_concrete_evidence(evidence):
            continue
        facts.append(
            LineItemCandidateFact(
                line_item_type="service_line",
                ordinal=int(item.get("ordinal") or len(facts) + 1),
                description=str(item["service_description"]),
                evidence=evidence,
                candidate_group="medical_eob.service_lines",
                code=item.get("procedure_code"),
                service_date=_date(item.get("service_date")),
                gross_amount=_money_amount(item.get("billed_amount")),
                net_amount=_money_amount(item.get("patient_responsibility")),
                currency=_money_currency(item.get("patient_responsibility")),
                confidence=confidence,
                authority_weight=AUTHORITY_WEIGHTS.get(source_engine, 0.5),
                status=status,
            )
        )
    return facts
