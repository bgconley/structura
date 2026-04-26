from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date
from typing import Any
from uuid import UUID

from lib.automation.rule_policy import validate_rule_definition

HIGH_STAKES_FAMILIES = {
    "medical_eob",
    "medical_bill",
    "insurance_document",
    "legal_contract",
    "legal_notice",
    "tax_document",
    "identity_document",
    "bank_statement",
    "financial_statement",
}
HIGH_STAKES_SENSITIVITY = {"medical", "legal", "financial", "pii", "highly_sensitive"}


@dataclass(frozen=True)
class FilingRuleDefinition:
    name: str
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    id: UUID | None = None
    description: str | None = None
    enabled: bool = True
    priority: int = 50
    review_required: bool = True


@dataclass(frozen=True)
class DocumentRuleContext:
    document_id: UUID
    document_family: str
    document_subtype: str | None
    counterparty: str | None
    tags: list[str]
    folder_ids: list[UUID]
    folder_paths: list[str]
    contacts: list[str]
    canonical_facts: dict[str, Any]
    review_status: str
    sensitivity: str
    search_text: str = ""
    amount_total: float | None = None
    document_date: date | None = None
    title: str | None = None


@dataclass(frozen=True)
class ConditionEvaluation:
    field: str
    op: str
    expected: Any
    observed: Any
    matched: bool
    evidence: dict[str, Any] = dataclass_field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "op": self.op,
            "expected": self.expected,
            "observed": self.observed,
            "matched": self.matched,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class RuleEvaluation:
    document_id: UUID
    matched: bool
    conditions: list[ConditionEvaluation]
    proposed_actions: list[dict[str, Any]]
    blocked_actions: list[dict[str, Any]]
    review_required: bool
    safety_reasons: list[str]

    def explanation(self) -> dict[str, Any]:
        return {
            "conditions": [condition.as_dict() for condition in self.conditions],
            "proposedActions": self.proposed_actions,
            "blockedActions": self.blocked_actions,
            "reviewRequired": self.review_required,
            "safetyReasons": self.safety_reasons,
        }


def evaluate_rule(
    rule: FilingRuleDefinition,
    context: DocumentRuleContext,
    *,
    writable_folder_ids: set[UUID] | None = None,
    writable_folder_paths: set[str] | None = None,
) -> RuleEvaluation:
    validated = validate_rule_definition(
        {
            "id": str(rule.id) if rule.id else None,
            "name": rule.name,
            "description": rule.description,
            "enabled": rule.enabled,
            "priority": rule.priority,
            "reviewRequired": rule.review_required,
            "conditions": rule.conditions,
            "actions": rule.actions,
        }
    )
    writable_ids = writable_folder_ids or set()
    writable_paths = writable_folder_paths or set()
    safety_reasons = _safety_reasons(context, bool(validated["review_required"]))

    if not validated["enabled"]:
        return RuleEvaluation(
            document_id=context.document_id,
            matched=False,
            conditions=[],
            proposed_actions=[],
            blocked_actions=[],
            review_required=bool(safety_reasons),
            safety_reasons=safety_reasons,
        )

    condition_results = [
        _evaluate_condition(condition, context) for condition in validated["conditions"]
    ]
    matched = all(condition.matched for condition in condition_results)
    proposed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    if matched:
        for action in validated["actions"]:
            blocked_reason = _blocked_action_reason(
                action,
                writable_folder_ids=writable_ids,
                writable_folder_paths=writable_paths,
            )
            if blocked_reason:
                blocked_action = dict(action)
                blocked_action["reason"] = blocked_reason
                blocked.append(blocked_action)
            else:
                proposed.append(dict(action))

    return RuleEvaluation(
        document_id=context.document_id,
        matched=matched,
        conditions=condition_results,
        proposed_actions=proposed,
        blocked_actions=blocked,
        review_required=bool(safety_reasons),
        safety_reasons=safety_reasons,
    )


def _evaluate_condition(
    condition: dict[str, Any],
    context: DocumentRuleContext,
) -> ConditionEvaluation:
    field_name = str(condition["field"])
    observed = _observed_value(field_name, context)
    op = str(condition["op"])
    expected = condition.get("value")
    matched = _match(op=op, observed=observed, expected=expected)
    return ConditionEvaluation(
        field=field_name,
        op=op,
        expected=expected,
        observed=_serializable(observed),
        matched=matched,
        evidence={"source": field_name},
    )


def _observed_value(field_name: str, context: DocumentRuleContext) -> Any:
    if field_name.startswith("canonical."):
        return context.canonical_facts.get(field_name.removeprefix("canonical."))
    return {
        "document_family": context.document_family,
        "document_subtype": context.document_subtype,
        "counterparty": context.counterparty,
        "contacts": context.contacts,
        "tags": context.tags,
        "folders": context.folder_paths,
        "folder_paths": context.folder_paths,
        "folder_ids": [str(folder_id) for folder_id in context.folder_ids],
        "document_date": context.document_date,
        "amount_total": context.amount_total,
        "review_status": context.review_status,
        "sensitivity": context.sensitivity,
        "search_text": context.search_text,
    }.get(field_name)


def _match(*, op: str, observed: Any, expected: Any) -> bool:
    if op == "exists":
        return observed is not None and observed != "" and observed != []
    if op == "eq":
        return bool(_normalize_scalar(observed) == _normalize_scalar(expected))
    if op == "neq":
        return bool(_normalize_scalar(observed) != _normalize_scalar(expected))
    if op == "contains":
        return _contains(observed, expected)
    if op == "in":
        expected_values = expected if isinstance(expected, list) else [expected]
        return any(
            _normalize_scalar(observed) == _normalize_scalar(item) for item in expected_values
        )
    if op == "gte":
        return _compare(observed, expected, lambda left, right: left >= right)
    if op == "lte":
        return _compare(observed, expected, lambda left, right: left <= right)
    if op == "regex":
        return isinstance(expected, str) and bool(
            re.search(expected, str(observed or ""), flags=re.IGNORECASE)
        )
    return False


def _contains(observed: Any, expected: Any) -> bool:
    needle = str(expected).casefold()
    if isinstance(observed, list):
        return any(needle in str(item).casefold() for item in observed)
    return needle in str(observed or "").casefold()


def _compare(observed: Any, expected: Any, comparator: Any) -> bool:
    try:
        return bool(comparator(float(observed), float(expected)))
    except (TypeError, ValueError):
        return str(observed or "") >= str(expected or "")


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def _blocked_action_reason(
    action: dict[str, Any],
    *,
    writable_folder_ids: set[UUID],
    writable_folder_paths: set[str],
) -> str | None:
    if action["type"] not in {"add_folder", "set_primary_folder"}:
        return None
    folder_id = action.get("folder_id") or action.get("folderId")
    folder_path = action.get("folder_path") or action.get("folderPath")
    if folder_id and UUID(str(folder_id)) in writable_folder_ids:
        return None
    if folder_path and str(folder_path) in writable_folder_paths:
        return None
    return "Folder is not writable for this actor."


def _safety_reasons(context: DocumentRuleContext, rule_review_required: bool) -> list[str]:
    reasons: list[str] = []
    if rule_review_required:
        reasons.append("rule_requires_review")
    if context.sensitivity in HIGH_STAKES_SENSITIVITY:
        reasons.append(context.sensitivity)
    if context.document_family in HIGH_STAKES_FAMILIES:
        reasons.append(context.document_family)
    return reasons


def _serializable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_serializable(item) for item in value]
    return value
