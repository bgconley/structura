from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from lib.extraction.claims import Claim
from lib.extraction.quality_outcomes import QualityOutcome


@dataclass(frozen=True)
class ClaimFieldProjection:
    canonical_key: str
    container: str
    field_name: str


@dataclass(frozen=True)
class ClaimLineItemProjection:
    canonical_prefix: str
    field_map: dict[str, str]


@dataclass(frozen=True)
class ClaimFamilyRegistry:
    family: str
    field_projections: tuple[ClaimFieldProjection, ...]
    line_item_projection: ClaimLineItemProjection | None = None


@dataclass(frozen=True)
class ClaimResolutionDecision:
    canonical_key: str
    decision: str
    reason_code: str
    selected_claim_id: str | None
    rejected_claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimFamilyProjection:
    family: str
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    line_items: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[ClaimResolutionDecision] = field(default_factory=list)
    quality_outcome: QualityOutcome = "insufficient_signal"


SOURCE_PRECEDENCE: dict[str, int] = {
    "granite": 30,
    "docling": 20,
    "qwen": 10,
}

INVOICE_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="invoice",
    field_projections=(
        ClaimFieldProjection("invoice.invoice_number", "invoice", "invoice_number"),
        ClaimFieldProjection("invoice.issue_date", "invoice", "issued_on"),
        ClaimFieldProjection("invoice.due_date", "invoice", "due_on"),
        ClaimFieldProjection("invoice.subtotal", "totals", "subtotal"),
        ClaimFieldProjection("invoice.tax_total", "totals", "tax_total"),
        ClaimFieldProjection("invoice.total_amount", "totals", "total"),
        ClaimFieldProjection("invoice.balance_due", "totals", "balance_due"),
        ClaimFieldProjection("invoice.amount_paid", "totals", "amount_paid"),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="invoice.line_item.",
        field_map={
            "description": "description",
            "code": "code",
            "quantity": "quantity",
            "unit": "unit",
            "unit_price": "unit_price",
            "gross_amount": "gross_amount",
            "tax_amount": "tax_amount",
            "amount": "amount",
            "service_date": "service_date",
            "category_hint": "category_hint",
        },
    ),
)

RECEIPT_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="receipt",
    field_projections=(
        ClaimFieldProjection("receipt.merchant.display_name", "merchant", "display_name"),
        ClaimFieldProjection("receipt.transaction.date_local", "transaction", "date_local"),
        ClaimFieldProjection("receipt.transaction.subtotal", "transaction", "subtotal"),
        ClaimFieldProjection("receipt.transaction.tax", "transaction", "tax"),
        ClaimFieldProjection("receipt.transaction.tip", "transaction", "tip"),
        ClaimFieldProjection("receipt.transaction.total", "transaction", "total"),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="receipt.line_item.",
        field_map={
            "description": "description",
            "code": "sku",
            "quantity": "quantity",
            "unit": "unit",
            "unit_price": "unit_price",
            "amount": "amount",
            "category_hint": "category_hint",
        },
    ),
)

MEDICAL_EOB_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="medical_eob",
    field_projections=(
        ClaimFieldProjection("medical_eob.payer.display_name", "payer", "display_name"),
        ClaimFieldProjection("medical_eob.patient.display_name", "patient", "display_name"),
        ClaimFieldProjection("medical_eob.provider.display_name", "provider", "display_name"),
        ClaimFieldProjection("medical_eob.claim_number", "claim", "claim_number"),
        ClaimFieldProjection("medical_eob.received_on", "claim", "received_on"),
        ClaimFieldProjection("medical_eob.processed_on", "claim", "processed_on"),
        ClaimFieldProjection("medical_eob.group_number", "claim", "group_number"),
        ClaimFieldProjection("medical_eob.member_id", "claim", "member_id"),
        ClaimFieldProjection(
            "medical_eob.total_billed",
            "financial_summary",
            "total_billed",
        ),
        ClaimFieldProjection(
            "medical_eob.total_allowed",
            "financial_summary",
            "total_allowed",
        ),
        ClaimFieldProjection(
            "medical_eob.total_plan_paid",
            "financial_summary",
            "total_plan_paid",
        ),
        ClaimFieldProjection(
            "medical_eob.total_patient_responsibility",
            "financial_summary",
            "total_patient_responsibility",
        ),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="medical_eob.line_item.",
        field_map={
            "description": "service_description",
            "code": "procedure_code",
            "quantity": "units",
            "gross_amount": "billed_amount",
            "amount": "patient_responsibility",
            "service_date": "service_date",
            "category_hint": "adjustment_reason",
        },
    ),
)

CLAIM_FAMILY_REGISTRIES: dict[str, ClaimFamilyRegistry] = {
    INVOICE_CLAIM_REGISTRY.family: INVOICE_CLAIM_REGISTRY,
    RECEIPT_CLAIM_REGISTRY.family: RECEIPT_CLAIM_REGISTRY,
    MEDICAL_EOB_CLAIM_REGISTRY.family: MEDICAL_EOB_CLAIM_REGISTRY,
}


def resolve_claims_for_family(
    *,
    family: str,
    claims: list[Claim],
) -> ClaimFamilyProjection:
    registry = CLAIM_FAMILY_REGISTRIES.get(family)
    if registry is None:
        return _resolve_document_observations(requested_family=family, claims=claims)
    fields: dict[str, dict[str, Any]] = {}
    decisions: list[ClaimResolutionDecision] = []
    for field_projection in registry.field_projections:
        selected, decision = _resolve_key(
            field_projection.canonical_key,
            [claim for claim in claims if claim.canonical_key == field_projection.canonical_key],
        )
        if decision is not None:
            decisions.append(decision)
        if selected is None:
            continue
        fields.setdefault(field_projection.container, {})[field_projection.field_name] = (
            selected.typed_value
        )
    line_items: list[dict[str, Any]] = []
    if registry.line_item_projection is not None:
        resolved_line_items, line_decisions = _resolve_line_items(
            registry.line_item_projection,
            claims,
        )
        line_items = resolved_line_items
        decisions.extend(line_decisions)
    decisions = sorted(decisions, key=lambda decision: decision.canonical_key)
    return ClaimFamilyProjection(
        family=family,
        fields=fields,
        line_items=line_items,
        decisions=decisions,
        quality_outcome=_quality_outcome(
            decisions=decisions,
            has_material_output=bool(fields or line_items),
            review_only=False,
        ),
    )


def _resolve_document_observations(
    *,
    requested_family: str,
    claims: list[Claim],
) -> ClaimFamilyProjection:
    grouped: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        grouped[claim.canonical_key].append(claim)

    observations: list[dict[str, Any]] = []
    decisions: list[ClaimResolutionDecision] = []
    for canonical_key in sorted(grouped):
        selected, decision = _resolve_key(canonical_key, grouped[canonical_key])
        if decision is not None:
            decisions.append(decision)
        if selected is None:
            continue
        observations.append(
            _observation_from_claim(
                selected,
                requested_family=requested_family,
            )
        )
    return ClaimFamilyProjection(
        family="document_observation",
        observations=observations,
        decisions=decisions,
        quality_outcome=_quality_outcome(
            decisions=decisions,
            has_material_output=bool(observations),
            review_only=True,
            no_extraction_target=requested_family == "no_extraction_target",
        ),
    )


def _resolve_line_items(
    projection: ClaimLineItemProjection,
    claims: list[Claim],
) -> tuple[list[dict[str, Any]], list[ClaimResolutionDecision]]:
    grouped: dict[str, dict[str, list[Claim]]] = defaultdict(lambda: defaultdict(list))
    group_order: list[str] = []
    for claim in claims:
        if not claim.canonical_key.startswith(projection.canonical_prefix):
            continue
        suffix = claim.canonical_key.removeprefix(projection.canonical_prefix)
        field_name = projection.field_map.get(suffix)
        if field_name is None:
            continue
        group_id = claim.group_id or _anchor_group_id(claim)
        if group_id not in grouped:
            group_order.append(group_id)
        grouped[group_id][field_name].append(claim)

    line_items: list[dict[str, Any]] = []
    decisions: list[ClaimResolutionDecision] = []
    for group_id in group_order:
        line_item: dict[str, Any] = {}
        evidence: list[dict[str, Any]] = []
        for field_name, field_claims in sorted(grouped[group_id].items()):
            selected, decision = _resolve_key(
                field_claims[0].canonical_key,
                field_claims,
            )
            if decision is not None:
                decisions.append(decision)
            if selected is None:
                continue
            line_item[field_name] = selected.typed_value
            if selected.evidence and not evidence:
                evidence = [_clean_evidence(item) for item in selected.evidence]
        if evidence:
            line_item["evidence"] = evidence
        if _line_item_has_value(line_item):
            line_items.append(line_item)
    return line_items, decisions


def _resolve_key(
    canonical_key: str,
    claims: list[Claim],
) -> tuple[Claim | None, ClaimResolutionDecision | None]:
    if not claims:
        return None, None
    ordered = sorted(claims, key=_claim_sort_key)
    selected = ordered[0]
    rejected = tuple(claim.claim_id for claim in ordered[1:])
    unique_values = {_stable_value_key(claim.typed_value) for claim in ordered}
    reason_code = (
        "single_source"
        if len(ordered) == 1
        else "multi_source_agreement"
        if len(unique_values) == 1
        else "source_precedence_conflict"
    )
    decision = "accepted" if reason_code != "source_precedence_conflict" else "needs_review"
    return selected, ClaimResolutionDecision(
        canonical_key=canonical_key,
        decision=decision,
        reason_code=reason_code,
        selected_claim_id=selected.claim_id,
        rejected_claim_ids=rejected,
    )


def _claim_sort_key(claim: Claim) -> tuple[int, float, str]:
    return (
        -SOURCE_PRECEDENCE.get(claim.source_engine, 0),
        -(claim.confidence or 0.0),
        claim.claim_id,
    )


def _quality_outcome(
    *,
    decisions: list[ClaimResolutionDecision],
    has_material_output: bool,
    review_only: bool,
    no_extraction_target: bool = False,
) -> QualityOutcome:
    if no_extraction_target and not has_material_output:
        return "no_extraction_target"
    if not has_material_output:
        return "insufficient_signal"
    if review_only or any(decision.decision == "needs_review" for decision in decisions):
        return "needs_human_review"
    return "extracted_cleanly"


def _stable_value_key(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _observation_from_claim(
    claim: Claim,
    *,
    requested_family: str,
) -> dict[str, Any]:
    observation_family, field_name = _observation_family_and_field(
        canonical_key=claim.canonical_key,
        requested_family=requested_family,
    )
    payload: dict[str, Any] = {
        "family": observation_family,
        "field_name": field_name,
        "value": claim.typed_value,
        "value_type": _observation_value_type(claim.typed_value),
        "source_text": _source_text(claim.raw_value),
        "confidence": claim.confidence,
        "evidence": _observation_evidence(claim),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _observation_family_and_field(
    *,
    canonical_key: str,
    requested_family: str,
) -> tuple[str | None, str]:
    family, separator, field_name = canonical_key.partition(".")
    if separator and field_name:
        return family, field_name
    if requested_family != "document_observation":
        return requested_family, canonical_key
    return None, canonical_key


def _observation_value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, dict | list):
        return "json"
    return "string"


def _source_text(raw_value: str) -> str | None:
    if not raw_value:
        return None
    import json

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, str):
        return parsed[:500]
    return raw_value[:500]


def _observation_evidence(claim: Claim) -> list[dict[str, Any]]:
    evidence = [_clean_evidence(item) for item in claim.evidence]
    evidence = [item for item in evidence if item]
    if evidence:
        return evidence
    anchor = _clean_evidence(claim.anchor.as_json())
    return [anchor] if anchor else []


def _anchor_group_id(claim: Claim) -> str:
    return _stable_value_key(claim.anchor.as_json())


def _line_item_has_value(item: dict[str, Any]) -> bool:
    return any(
        item.get(key) not in (None, "")
        for key in (
            "description",
            "code",
            "quantity",
            "unit_price",
            "gross_amount",
            "tax_amount",
            "amount",
            "service_description",
            "procedure_code",
            "units",
            "billed_amount",
            "patient_responsibility",
        )
    )


def _clean_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value not in (None, "", [])}
