from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from lib.extraction.claim_decisions import ClaimResolutionDecision
from lib.extraction.claim_registry import (
    ClaimArithmeticInvariant,
    ClaimLineItemSumInvariant,
    ClaimMoneyUpperBoundInvariant,
)
from lib.extraction.claims import Claim

MONEY_TOLERANCE = Decimal("0.02")


def apply_claim_invariants(
    *,
    arithmetic_invariants: tuple[ClaimArithmeticInvariant, ...],
    line_item_sum_invariants: tuple[ClaimLineItemSumInvariant, ...],
    money_upper_bound_invariants: tuple[ClaimMoneyUpperBoundInvariant, ...],
    selected_claims: dict[str, Claim],
    line_items: list[dict[str, Any]],
    decisions: list[ClaimResolutionDecision],
) -> list[ClaimResolutionDecision]:
    decisions = _apply_arithmetic_invariants(
        invariants=arithmetic_invariants,
        selected_claims=selected_claims,
        decisions=decisions,
    )
    decisions = _apply_money_upper_bound_invariants(
        invariants=money_upper_bound_invariants,
        selected_claims=selected_claims,
        decisions=decisions,
    )
    return _apply_line_item_sum_invariants(
        invariants=line_item_sum_invariants,
        selected_claims=selected_claims,
        line_items=line_items,
        decisions=decisions,
    )


def _apply_arithmetic_invariants(
    *,
    invariants: tuple[ClaimArithmeticInvariant, ...],
    selected_claims: dict[str, Claim],
    decisions: list[ClaimResolutionDecision],
) -> list[ClaimResolutionDecision]:
    updated = decisions
    for invariant in invariants:
        target_claim = selected_claims.get(invariant.target_key)
        target_amount = _claim_money_amount(target_claim)
        addend_amounts = [
            _claim_money_amount(selected_claims.get(addend_key))
            for addend_key in invariant.addend_keys
        ]
        currencies = [
            _claim_money_currency(claim)
            for claim in (
                target_claim,
                *(selected_claims.get(addend_key) for addend_key in invariant.addend_keys),
            )
        ]
        if (
            target_claim is None
            or target_amount is None
            or any(amount is None for amount in addend_amounts)
        ):
            continue
        if _has_currency_conflict(currencies):
            updated = _demote_decision(
                decisions=updated,
                canonical_key=invariant.target_key,
                selected_claim_id=target_claim.claim_id,
                reason_code=invariant.currency_reason_code,
            )
            continue
        expected = sum((amount for amount in addend_amounts if amount is not None), Decimal("0"))
        if target_amount == expected:
            continue
        updated = _demote_decision(
            decisions=updated,
            canonical_key=invariant.target_key,
            selected_claim_id=target_claim.claim_id,
            reason_code=invariant.reason_code,
        )
    return updated


def _apply_money_upper_bound_invariants(
    *,
    invariants: tuple[ClaimMoneyUpperBoundInvariant, ...],
    selected_claims: dict[str, Claim],
    decisions: list[ClaimResolutionDecision],
) -> list[ClaimResolutionDecision]:
    updated = decisions
    for invariant in invariants:
        target_claim = selected_claims.get(invariant.target_key)
        target_amount = _claim_money_amount(target_claim)
        addend_amounts = [
            _claim_money_amount(selected_claims.get(addend_key))
            for addend_key in invariant.addend_keys
        ]
        currencies = [
            _claim_money_currency(claim)
            for claim in (
                target_claim,
                *(selected_claims.get(addend_key) for addend_key in invariant.addend_keys),
            )
        ]
        if (
            target_claim is None
            or target_amount is None
            or any(amount is None for amount in addend_amounts)
        ):
            continue
        if _has_currency_conflict(currencies):
            updated = _demote_decision(
                decisions=updated,
                canonical_key=invariant.target_key,
                selected_claim_id=target_claim.claim_id,
                reason_code=invariant.currency_reason_code,
            )
            continue
        measured = sum((amount for amount in addend_amounts if amount is not None), Decimal("0"))
        if measured - target_amount <= MONEY_TOLERANCE:
            continue
        updated = _demote_decision(
            decisions=updated,
            canonical_key=invariant.target_key,
            selected_claim_id=target_claim.claim_id,
            reason_code=invariant.reason_code,
        )
    return updated


def _apply_line_item_sum_invariants(
    *,
    invariants: tuple[ClaimLineItemSumInvariant, ...],
    selected_claims: dict[str, Claim],
    line_items: list[dict[str, Any]],
    decisions: list[ClaimResolutionDecision],
) -> list[ClaimResolutionDecision]:
    updated = decisions
    for invariant in invariants:
        target_claim = selected_claims.get(invariant.target_key)
        target_amount = _claim_money_amount(target_claim)
        if target_claim is None or target_amount is None or not line_items:
            continue
        line_amounts: list[Decimal] = []
        currencies = [_claim_money_currency(target_claim)]
        incomplete = False
        for item in line_items:
            value = item.get(invariant.line_item_field)
            amount = _money_amount(value)
            if amount is None:
                incomplete = True
                break
            line_amounts.append(amount)
            currencies.append(_money_currency(value))
        if incomplete or not line_amounts:
            continue
        if _has_currency_conflict(currencies):
            updated = _demote_decision(
                decisions=updated,
                canonical_key=invariant.target_key,
                selected_claim_id=target_claim.claim_id,
                reason_code=invariant.currency_reason_code,
            )
            continue
        expected = sum(line_amounts, Decimal("0"))
        if target_amount == expected:
            continue
        updated = _demote_decision(
            decisions=updated,
            canonical_key=invariant.target_key,
            selected_claim_id=target_claim.claim_id,
            reason_code=invariant.reason_code,
        )
    return updated


def _demote_decision(
    *,
    decisions: list[ClaimResolutionDecision],
    canonical_key: str,
    selected_claim_id: str,
    reason_code: str,
) -> list[ClaimResolutionDecision]:
    replaced = False
    updated: list[ClaimResolutionDecision] = []
    for decision in decisions:
        if decision.canonical_key != canonical_key:
            updated.append(decision)
            continue
        replaced = True
        updated.append(
            ClaimResolutionDecision(
                canonical_key=canonical_key,
                decision="needs_review",
                reason_code=reason_code,
                selected_claim_id=decision.selected_claim_id or selected_claim_id,
                rejected_claim_ids=decision.rejected_claim_ids,
            )
        )
    if replaced:
        return updated
    return [
        *updated,
        ClaimResolutionDecision(
            canonical_key=canonical_key,
            decision="needs_review",
            reason_code=reason_code,
            selected_claim_id=selected_claim_id,
        ),
    ]


def _claim_money_amount(claim: Claim | None) -> Decimal | None:
    if claim is None:
        return None
    return _money_amount(claim.typed_value)


def _money_amount(value: Any) -> Decimal | None:
    if not isinstance(value, dict):
        return None
    amount = value.get("amount")
    if amount is None:
        return None
    try:
        return Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _claim_money_currency(claim: Claim | None) -> str | None:
    if claim is None:
        return None
    return _money_currency(claim.typed_value)


def _money_currency(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    currency = value.get("currency")
    if currency in (None, ""):
        return None
    return str(currency).upper()


def _has_currency_conflict(currencies: list[str | None]) -> bool:
    explicit = {currency for currency in currencies if currency is not None}
    return len(explicit) > 1
