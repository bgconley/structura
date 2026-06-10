from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from lib.extraction.candidate_deduplication import (
    dedupe_line_item_candidates,
    dedupe_observation_candidates,
)
from lib.extraction.candidate_quality import (
    reject_line_item,
    reject_observation,
    reject_scalar_candidate,
)
from lib.extraction.candidate_value_parsing import (
    candidate_status,
    date_value,
    empty_observation_value,
    grid_only_observation,
    money_amount,
    money_currency,
    number_value,
)
from lib.extraction.claim_registry import CLAIM_FAMILY_REGISTRIES
from lib.extraction.claim_resolver import ClaimFamilyProjection, resolve_claims_for_family
from lib.extraction.claims import Claim
from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.models import (
    CandidateFact,
    LineItemCandidateFact,
    ObservationCandidateFact,
    ValidationReport,
)
from lib.extraction.normalization import AUTHORITY_WEIGHTS

_FIRST_CLASS_CANDIDATE_FAMILIES = {"invoice", "receipt", "medical_eob"}


def field_candidates_from_claims(
    *,
    document_id: UUID,
    family: str,
    claims: Sequence[Claim],
    validation: ValidationReport,
    source_engine: str,
    require_concrete_evidence: bool = False,
) -> list[CandidateFact]:
    del document_id
    if family not in _FIRST_CLASS_CANDIDATE_FAMILIES:
        return []
    registry = CLAIM_FAMILY_REGISTRIES.get(family)
    if registry is None:
        return []
    projection = resolve_claims_for_family(family=family, claims=list(claims))
    selected_by_key = _selected_claims_by_key(projection, claims)
    candidates: list[CandidateFact] = []
    for field_projection in registry.field_projections:
        claim = selected_by_key.get(field_projection.canonical_key)
        if claim is None:
            continue
        candidate = _field_candidate_from_claim(
            claim,
            validation=validation,
            source_engine=source_engine,
            require_concrete_evidence=require_concrete_evidence,
            decision_status=_decision_status(projection, field_projection.canonical_key),
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def line_item_candidates_from_claims(
    *,
    family: str,
    claims: Sequence[Claim],
    validation: ValidationReport,
    source_engine: str,
    require_concrete_evidence: bool = False,
) -> list[LineItemCandidateFact]:
    if family not in _FIRST_CLASS_CANDIDATE_FAMILIES:
        return []
    projection = resolve_claims_for_family(family=family, claims=list(claims))
    line_item_type = _line_item_type(family)
    if line_item_type is None:
        return []
    candidates: list[LineItemCandidateFact] = []
    for item in projection.line_items:
        candidate = _line_item_candidate_from_projection(
            item,
            family=family,
            line_item_type=line_item_type,
            validation=validation,
            source_engine=source_engine,
            require_concrete_evidence=require_concrete_evidence,
        )
        if candidate is not None:
            candidates.append(candidate)
    return dedupe_line_item_candidates(candidates)


def observation_candidates_from_claims(
    *,
    family: str,
    claims: Sequence[Claim],
    validation: ValidationReport,
    require_concrete_evidence: bool = False,
) -> list[ObservationCandidateFact]:
    if family in _FIRST_CLASS_CANDIDATE_FAMILIES:
        return []
    projection = resolve_claims_for_family(family="document_observation", claims=list(claims))
    candidates: list[ObservationCandidateFact] = []
    for item in projection.observations:
        candidate = _observation_candidate_from_projection(
            item,
            validation=validation,
            require_concrete_evidence=require_concrete_evidence,
        )
        if candidate is not None:
            candidates.append(candidate)
    return dedupe_observation_candidates(candidates)


def _selected_claims_by_key(
    projection: ClaimFamilyProjection,
    claims: Sequence[Claim],
) -> dict[str, Claim]:
    claims_by_id = {claim.claim_id: claim for claim in claims}
    selected: dict[str, Claim] = {}
    for decision in projection.decisions:
        if decision.selected_claim_id is None:
            continue
        claim = claims_by_id.get(decision.selected_claim_id)
        if claim is not None:
            selected[decision.canonical_key] = claim
    return selected


def _decision_status(projection: ClaimFamilyProjection, canonical_key: str) -> str | None:
    for decision in projection.decisions:
        if decision.canonical_key == canonical_key and decision.decision != "accepted":
            return "needs_review"
    return None


def _field_candidate_from_claim(
    claim: Claim,
    *,
    validation: ValidationReport,
    source_engine: str,
    require_concrete_evidence: bool,
    decision_status: str | None,
) -> CandidateFact | None:
    value_type, value = _candidate_value(claim)
    if value in (None, ""):
        return None
    rejected, _reason = reject_scalar_candidate(value)
    if rejected:
        return None
    evidence = _claim_evidence(claim)
    if require_concrete_evidence and not has_concrete_evidence(evidence):
        return None
    return CandidateFact(
        field_path=claim.canonical_key,
        value_type=value_type,
        value=value,
        currency=money_currency(value) if value_type == "money" else None,
        evidence=evidence,
        confidence=claim.confidence,
        authority_weight=_authority_weight(source_engine, claim),
        validation=validation.as_json(),
        status=decision_status
        or candidate_status(validation, evidence, source_engine=source_engine),
    )


def _line_item_candidate_from_projection(
    item: dict[str, Any],
    *,
    family: str,
    line_item_type: str,
    validation: ValidationReport,
    source_engine: str,
    require_concrete_evidence: bool,
) -> LineItemCandidateFact | None:
    description = item.get("description") or item.get("service_description")
    if description in (None, ""):
        return None
    rejected, _reason = reject_line_item(item)
    if rejected:
        return None
    evidence = _projection_evidence(item)
    if require_concrete_evidence and not has_concrete_evidence(evidence):
        return None
    status = candidate_status(validation, evidence, source_engine=source_engine)
    if family == "medical_eob":
        patient_responsibility = item.get("patient_responsibility")
        return LineItemCandidateFact(
            line_item_type=line_item_type,
            ordinal=int(item.get("ordinal") or 1),
            description=str(description),
            evidence=evidence,
            candidate_group="medical_eob.service_lines",
            code=item.get("procedure_code"),
            service_date=date_value(item.get("service_date")),
            quantity=number_value(item.get("units")),
            gross_amount=money_amount(item.get("billed_amount")),
            allowed_amount=money_amount(item.get("allowed_amount")),
            plan_paid_amount=money_amount(item.get("plan_paid")),
            net_amount=money_amount(patient_responsibility),
            currency=money_currency(patient_responsibility),
            category_hint=item.get("adjustment_reason"),
            validation=validation.as_json(),
            status=status,
        )
    amount = item.get("amount")
    gross_amount = item.get("gross_amount") or amount
    return LineItemCandidateFact(
        line_item_type=line_item_type,
        ordinal=int(item.get("ordinal") or 1),
        description=str(description),
        evidence=evidence,
        candidate_group=f"{line_item_type}.default",
        code=item.get("code") or item.get("sku"),
        service_date=date_value(item.get("service_date")),
        quantity=number_value(item.get("quantity")),
        unit=item.get("unit"),
        unit_price=money_amount(item.get("unit_price")),
        gross_amount=money_amount(gross_amount),
        discount_amount=money_amount(item.get("discount")),
        tax_amount=money_amount(item.get("tax_amount")),
        net_amount=money_amount(amount),
        currency=money_currency(amount) or money_currency(gross_amount),
        category_hint=item.get("category_hint") or item.get("tax_category_hint"),
        validation=validation.as_json(),
        status=status,
    )


def _observation_candidate_from_projection(
    item: dict[str, Any],
    *,
    validation: ValidationReport,
    require_concrete_evidence: bool,
) -> ObservationCandidateFact | None:
    field_name = item.get("field_name")
    if not field_name:
        return None
    value = item.get("value")
    rejected, _reason = reject_observation(str(field_name), value)
    if rejected:
        return None
    if empty_observation_value(value) or grid_only_observation(field_name, value):
        return None
    evidence = _projection_evidence(item)
    if require_concrete_evidence and not has_concrete_evidence(evidence):
        return None
    return ObservationCandidateFact(
        observation_family=str(item["family"]) if item.get("family") not in (None, "") else None,
        field_name=str(field_name),
        value_type=str(item.get("value_type") or "string"),
        value=value,
        evidence=evidence,
        confidence=item.get("confidence"),
        validation=validation.as_json(),
        status="needs_review",
        metadata={"source_text": item.get("source_text")},
    )


def _candidate_value(claim: Claim) -> tuple[str, Any]:
    if claim.value_type == "money":
        return "money", claim.typed_value
    if claim.value_type == "date":
        return "date", date_value(claim.typed_value)
    if claim.value_type in {"number", "quantity"}:
        return "number", number_value(claim.typed_value)
    if claim.value_type == "boolean":
        return "boolean", claim.typed_value
    if claim.value_type == "object":
        return "json", claim.typed_value
    return "string", claim.typed_value


def _claim_evidence(claim: Claim) -> list[dict[str, Any]]:
    evidence = [_clean_evidence(item) for item in claim.evidence]
    evidence = [item for item in evidence if item]
    if evidence:
        return evidence
    anchor = _clean_evidence(claim.anchor.as_json())
    return [anchor] if anchor else []


def _projection_evidence(item: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = item.get("evidence")
    if not isinstance(evidence, list):
        return []
    return [_clean_evidence(ref) for ref in evidence if isinstance(ref, dict)]


def _clean_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value not in (None, "", [])}


def _authority_weight(source_engine: str, claim: Claim) -> float:
    return AUTHORITY_WEIGHTS.get(source_engine, AUTHORITY_WEIGHTS.get(claim.source_engine, 0.5))


def _line_item_type(family: str) -> str | None:
    return {
        "invoice": "invoice_item",
        "receipt": "receipt_item",
        "medical_eob": "service_line",
    }.get(family)
