from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from lib.extraction.claims import Claim


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
    decisions: list[ClaimResolutionDecision] = field(default_factory=list)


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

CLAIM_FAMILY_REGISTRIES: dict[str, ClaimFamilyRegistry] = {
    INVOICE_CLAIM_REGISTRY.family: INVOICE_CLAIM_REGISTRY,
}


def resolve_claims_for_family(
    *,
    family: str,
    claims: list[Claim],
) -> ClaimFamilyProjection:
    registry = CLAIM_FAMILY_REGISTRIES[family]
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
    return ClaimFamilyProjection(
        family=family,
        fields=fields,
        line_items=line_items,
        decisions=sorted(decisions, key=lambda decision: decision.canonical_key),
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
                f"{projection.canonical_prefix}{field_name}",
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


def _stable_value_key(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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
        )
    )


def _clean_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value not in (None, "", [])}
