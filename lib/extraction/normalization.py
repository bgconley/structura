from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date, datetime
from typing import Any
from uuid import UUID

from lib.extraction.candidate_quality import (
    reject_line_item,
    reject_observation,
    reject_scalar_candidate,
)
from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.model_output_normalization import (
    invoice_line_item_dicts_from_payload,
    observation_dicts_from_payload,
)
from lib.extraction.models import (
    CandidateFact,
    Evidence,
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
                metadata={"source_text": item.get("source_text")},
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


def _dedupe_line_item_candidates(
    facts: list[LineItemCandidateFact],
) -> list[LineItemCandidateFact]:
    exact: dict[tuple[Any, ...], LineItemCandidateFact] = {}
    for fact in facts:
        key = _line_item_exact_key(fact)
        current = exact.get(key)
        if current is None or _line_item_richness(fact) > _line_item_richness(current):
            exact[key] = fact

    unique = list(exact.values())
    rich_sparse_keys = {
        _line_item_sparse_key(fact) for fact in unique if _line_item_has_meaningful_detail(fact)
    }
    filtered = [
        fact
        for fact in unique
        if not (_line_item_is_sparse(fact) and _line_item_sparse_key(fact) in rich_sparse_keys)
    ]
    return [replace(fact, ordinal=index + 1) for index, fact in enumerate(filtered)]


def _line_item_exact_key(fact: LineItemCandidateFact) -> tuple[Any, ...]:
    return (
        _normalized_text_key(fact.line_item_type),
        _normalized_text_key(fact.description),
        _normalized_text_key(fact.code),
        _date_key(fact.service_date),
        _float_key(fact.quantity),
        _normalized_text_key(fact.unit),
        _float_key(fact.unit_price),
        _float_key(fact.gross_amount),
        _float_key(fact.discount_amount),
        _float_key(fact.tax_amount),
        _float_key(fact.net_amount),
        _normalized_text_key(fact.currency),
    )


def _line_item_sparse_key(fact: LineItemCandidateFact) -> tuple[Any, ...]:
    return (
        _normalized_text_key(fact.line_item_type),
        _normalized_text_key(fact.description),
        _normalized_text_key(fact.code),
    )


def _line_item_is_sparse(fact: LineItemCandidateFact) -> bool:
    return not _line_item_has_meaningful_detail(fact)


def _line_item_has_meaningful_detail(fact: LineItemCandidateFact) -> bool:
    return any(
        value is not None
        for value in (
            fact.code,
            fact.service_date,
            fact.quantity,
            fact.unit_price,
            fact.gross_amount,
            fact.discount_amount,
            fact.tax_amount,
            fact.net_amount,
        )
    )


def _line_item_richness(fact: LineItemCandidateFact) -> int:
    populated = (
        fact.code,
        fact.service_date,
        fact.quantity,
        fact.unit,
        fact.unit_price,
        fact.gross_amount,
        fact.discount_amount,
        fact.tax_amount,
        fact.net_amount,
        fact.currency,
        fact.category_hint,
    )
    return sum(value not in (None, "") for value in populated) + len(fact.evidence)


def _dedupe_observation_candidates(
    candidates: list[ObservationCandidateFact],
) -> list[ObservationCandidateFact]:
    deduped: dict[tuple[Any, ...], ObservationCandidateFact] = {}
    for candidate in candidates:
        key = _observation_key(candidate)
        if key not in deduped:
            deduped[key] = candidate
    return list(deduped.values())


def _observation_key(candidate: ObservationCandidateFact) -> tuple[Any, ...]:
    return (
        _normalized_text_key(candidate.observation_family),
        _normalized_text_key(candidate.field_name),
        _normalized_text_key(candidate.value_type),
        _json_key(candidate.value),
    )


def _empty_observation_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _grid_only_observation(field_name: Any, value: Any) -> bool:
    field = _normalized_text_key(field_name)
    if field == "dimensions":
        return True
    if field != "cells":
        return False
    return not _contains_textual_content(value)


def _contains_textual_content(value: Any) -> bool:
    if isinstance(value, str):
        return any(char.isalpha() for char in value)
    if isinstance(value, dict):
        return any(_contains_textual_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_textual_content(item) for item in value)
    return False


def _candidate_status(
    validation: ValidationReport,
    evidence: list[dict[str, Any]],
    *,
    source_engine: str,
) -> str:
    if (
        validation.needs_review
        or source_engine.startswith("qwen3_vl")
        or not has_concrete_evidence(evidence)
    ):
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
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
        if match:
            return float(match.group(0).replace(",", ""))
    return None


def _number_or_none(value: Any) -> float | None:
    try:
        return _number(value)
    except (TypeError, ValueError):
        return None


def _confidence_or_none(value: Any) -> float | None:
    confidence = _number_or_none(value)
    if confidence is None or not 0.0 <= confidence <= 1.0:
        return None
    return confidence


def _normalized_text_key(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _float_key(value: float | None) -> float | None:
    return round(float(value), 6) if value is not None else None


def _date_key(value: date | None) -> str:
    return value.isoformat() if isinstance(value, date) else ""


def _json_key(value: Any) -> str:
    return json.dumps(_json_key_value(value), sort_keys=True, separators=(",", ":"))


def _json_key_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalized_text_key(value)
    if isinstance(value, dict):
        return {str(key): _json_key_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_key_value(item) for item in value]
    return value


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
