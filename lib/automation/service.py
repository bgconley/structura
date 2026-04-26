from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation

from lib.auth import AuthPrincipal
from lib.automation import repository
from lib.automation.errors import AutomationError
from lib.automation.rule_engine import (
    DocumentRuleContext,
    FilingRuleDefinition,
    RuleEvaluation,
    evaluate_rule,
)
from lib.automation.rule_policy import RuleValidationError, validate_rule_definition
from lib.contracts import (
    FilingRule,
    FilingRuleApplyRequest,
    FilingRuleApplyResponse,
    FilingRuleDryRunRequest,
    FilingRuleDryRunResponse,
    FilingRuleEvaluation,
    FilingRuleWrite,
    FilingSuggestion,
)
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.organization import manual_filing
from lib.organization.policy import OrganizationError


def list_filing_rules(principal: AuthPrincipal) -> list[FilingRule]:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = repository.list_filing_rules(cur, household_id=household_id)
    return [_rule_from_row(row) for row in rows]


def upsert_filing_rule(payload: FilingRuleWrite, principal: AuthPrincipal) -> FilingRule:
    household_id = _require_household(principal)
    try:
        validated = validate_rule_definition(payload.model_dump(by_alias=True))
    except RuleValidationError as exc:
        raise AutomationError(422, str(exc)) from exc
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = repository.upsert_filing_rule(
                    cur,
                    rule_id=payload.id,
                    household_id=household_id,
                    name=str(validated["name"]),
                    description=validated.get("description")
                    if isinstance(validated.get("description"), str)
                    else None,
                    enabled=bool(validated["enabled"]),
                    priority=int(validated["priority"]),
                    review_required=bool(validated["review_required"]),
                    conditions=list(validated["conditions"]),
                    actions=list(validated["actions"]),
                    created_by_user_id=principal.user_id,
                )
                if not row:
                    raise AutomationError(404, "Filing rule not found")
                repository.record_audit(
                    cur,
                    entity_type="filing_rule",
                    entity_id=_uuid(row["id"]),
                    event_name="filing_rule.upserted",
                    actor_label=principal.email,
                    payload={"name": row["name"]},
                )
            conn.commit()
    except UniqueViolation as exc:
        raise AutomationError(409, "Filing rule already exists") from exc
    return _rule_from_row(row)


def dry_run_rule(
    *,
    rule_id: UUID,
    payload: FilingRuleDryRunRequest,
    principal: AuthPrincipal,
) -> FilingRuleDryRunResponse:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            rule = repository.get_filing_rule(cur, rule_id=rule_id, household_id=household_id)
            if not rule:
                raise AutomationError(404, "Filing rule not found")
            writable = repository.writable_folders(
                cur,
                household_id=household_id,
                user_id=principal.user_id,
            )
            rows = repository.document_context_rows(
                cur,
                access=_access_context(principal),
                document_ids=payload.document_ids,
            )
            items: list[FilingRuleEvaluation] = []
            for row in rows:
                evaluation = _evaluate_row(rule, row, writable)
                run = repository.insert_rule_run(
                    cur,
                    rule_id=_uuid(rule["id"]),
                    document_id=_uuid(row["id"]),
                    mode="dry_run",
                    matched=evaluation.matched,
                    proposed_actions=evaluation.proposed_actions,
                    blocked_actions=evaluation.blocked_actions,
                    applied_actions=[],
                    explanation=evaluation.explanation(),
                    decision_status="recorded",
                    actor_user_id=principal.user_id,
                )
                items.append(_evaluation_contract(rule, evaluation, run, status=None))
        conn.commit()
    return FilingRuleDryRunResponse(items=items)


def apply_rule(
    *,
    rule_id: UUID,
    payload: FilingRuleApplyRequest,
    principal: AuthPrincipal,
) -> FilingRuleApplyResponse:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            rule = repository.get_filing_rule(cur, rule_id=rule_id, household_id=household_id)
            if not rule:
                raise AutomationError(404, "Filing rule not found")
            writable = repository.writable_folders(
                cur,
                household_id=household_id,
                user_id=principal.user_id,
            )
            rows = repository.document_context_rows(
                cur,
                access=_access_context(principal),
                document_ids=[payload.document_id],
                limit=1,
            )
            if not rows:
                raise AutomationError(404, "Document not found")
            evaluation = _evaluate_row(rule, rows[0], writable)
            if evaluation.matched and evaluation.review_required:
                run = repository.insert_rule_run(
                    cur,
                    rule_id=_uuid(rule["id"]),
                    document_id=payload.document_id,
                    mode="suggest",
                    matched=True,
                    proposed_actions=evaluation.proposed_actions,
                    blocked_actions=evaluation.blocked_actions,
                    applied_actions=[],
                    explanation=evaluation.explanation(),
                    decision_status="pending",
                    actor_user_id=principal.user_id,
                )
                if run:
                    repository.create_or_refresh_suggestion_task(
                        cur,
                        document_id=payload.document_id,
                        run_id=_uuid(run["id"]),
                        rule_name=str(rule["name"]),
                        explanation=evaluation.explanation(),
                    )
                status = "suggested"
            elif evaluation.matched:
                applied = _apply_actions_with_manual_service(
                    document_id=payload.document_id,
                    actions=evaluation.proposed_actions,
                    principal=principal,
                )
                run = repository.insert_rule_run(
                    cur,
                    rule_id=_uuid(rule["id"]),
                    document_id=payload.document_id,
                    mode="apply",
                    matched=True,
                    proposed_actions=evaluation.proposed_actions,
                    blocked_actions=evaluation.blocked_actions,
                    applied_actions=applied,
                    explanation=evaluation.explanation(),
                    decision_status="applied",
                    actor_user_id=principal.user_id,
                )
                status = "applied"
            else:
                run = repository.insert_rule_run(
                    cur,
                    rule_id=_uuid(rule["id"]),
                    document_id=payload.document_id,
                    mode="apply",
                    matched=False,
                    proposed_actions=[],
                    blocked_actions=[],
                    applied_actions=[],
                    explanation=evaluation.explanation(),
                    decision_status="not_matched",
                    actor_user_id=principal.user_id,
                )
                status = "not_matched"
        conn.commit()
    response_payload = _evaluation_contract(
        rule,
        evaluation,
        run,
        status=status,
    ).model_dump(by_alias=True)
    response_payload["status"] = status
    return FilingRuleApplyResponse.model_validate(response_payload)


def list_filing_suggestions(principal: AuthPrincipal) -> list[FilingSuggestion]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = repository.list_pending_suggestions(cur, access=_access_context(principal))
    return [_suggestion_from_row(row) for row in rows]


def accept_suggestion(*, run_id: UUID, principal: AuthPrincipal) -> FilingRuleApplyResponse:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            run = repository.get_pending_suggestion(
                cur,
                run_id=run_id,
                household_id=household_id,
            )
            if not run:
                raise AutomationError(404, "Filing suggestion not found")
            document_id = _uuid(run["document_id"])
            applied = _apply_actions_with_manual_service(
                document_id=document_id,
                actions=list(run.get("proposed_actions_json") or []),
                principal=principal,
            )
            repository.mark_suggestion(
                cur,
                run_id=run_id,
                decision_status="accepted",
                applied_actions=applied,
            )
        conn.commit()
    return FilingRuleApplyResponse.model_validate(
        {
            "runId": run_id,
            "ruleId": run["rule_id"],
            "documentId": run["document_id"],
            "matched": bool(run["matched"]),
            "conditions": (run.get("explanation_json") or {}).get("conditions", []),
            "proposedActions": run.get("proposed_actions_json") or [],
            "blockedActions": run.get("blocked_actions_json") or [],
            "appliedActions": applied,
            "reviewRequired": False,
            "safetyReasons": (run.get("explanation_json") or {}).get("safetyReasons", []),
            "explanation": run.get("explanation_json") or {},
            "status": "accepted",
        }
    )


def reject_suggestion(*, run_id: UUID, principal: AuthPrincipal) -> dict[str, bool]:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            run = repository.get_pending_suggestion(
                cur,
                run_id=run_id,
                household_id=household_id,
            )
            if not run:
                raise AutomationError(404, "Filing suggestion not found")
            repository.mark_suggestion(cur, run_id=run_id, decision_status="rejected")
        conn.commit()
    return {"ok": True}


def defer_suggestion(*, run_id: UUID, principal: AuthPrincipal) -> dict[str, bool]:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            run = repository.get_pending_suggestion(
                cur,
                run_id=run_id,
                household_id=household_id,
            )
            if not run:
                raise AutomationError(404, "Filing suggestion not found")
            repository.mark_suggestion(cur, run_id=run_id, decision_status="deferred")
        conn.commit()
    return {"ok": True}


def _evaluate_row(
    rule: dict[str, Any],
    row: dict[str, Any],
    writable: list[dict[str, Any]],
) -> RuleEvaluation:
    context = _context_from_row(row)
    definition = FilingRuleDefinition(
        id=_uuid(rule["id"]),
        name=str(rule["name"]),
        description=rule.get("description") if isinstance(rule.get("description"), str) else None,
        enabled=bool(rule["enabled"]),
        priority=int(rule["priority"]),
        review_required=bool(rule["review_required"]),
        conditions=list(rule.get("conditions_json") or []),
        actions=list(rule.get("actions_json") or []),
    )
    return evaluate_rule(
        definition,
        context,
        writable_folder_ids={_uuid(item["id"]) for item in writable},
        writable_folder_paths={str(item["path"]) for item in writable},
    )


def _context_from_row(row: dict[str, Any]) -> DocumentRuleContext:
    return DocumentRuleContext(
        document_id=_uuid(row["id"]),
        title=str(row.get("title") or ""),
        document_family=str(row.get("document_family") or "generic"),
        document_subtype=(
            row.get("document_subtype") if isinstance(row.get("document_subtype"), str) else None
        ),
        counterparty=row.get("counterparty_display")
        if isinstance(row.get("counterparty_display"), str)
        else None,
        tags=[str(item) for item in row.get("tags") or []],
        folder_ids=[_uuid(item) for item in row.get("folder_ids") or []],
        folder_paths=[str(item) for item in row.get("folder_paths") or []],
        contacts=[str(item) for item in row.get("contacts") or []],
        canonical_facts=dict(row.get("canonical_facts") or {}),
        review_status=str(row.get("review_status") or "unreviewed"),
        sensitivity=str(row.get("sensitivity") or "normal"),
        search_text=str(row.get("search_text") or ""),
        amount_total=float(row["amount_total"]) if row.get("amount_total") is not None else None,
        document_date=(
            row.get("document_date") if isinstance(row.get("document_date"), date) else None
        ),
    )


def _apply_actions_with_manual_service(
    *,
    document_id: UUID,
    actions: list[dict[str, Any]],
    principal: AuthPrincipal,
) -> list[dict[str, Any]]:
    from lib.contracts import DocumentOrganizationWrite

    current_folders: list[UUID] = []
    primary_folder: UUID | None = None
    current_tags: list[str] = []
    detail = None
    try:
        from lib.documents.read_model import get_document_detail

        detail = get_document_detail(document_id, _access_context(principal))
    except Exception as exc:
        raise AutomationError(404, "Document not found") from exc
    if not detail:
        raise AutomationError(404, "Document not found")
    current_folders = list(detail.folder_ids)
    primary_folder = detail.primary_folder_id
    current_tags = list(detail.tags)

    for action in actions:
        if action["type"] == "add_folder":
            folder_id = _action_folder_id(action)
            if folder_id and folder_id not in current_folders:
                current_folders.append(folder_id)
                primary_folder = primary_folder or folder_id
        elif action["type"] == "set_primary_folder":
            folder_id = _action_folder_id(action)
            if folder_id:
                if folder_id not in current_folders:
                    current_folders.append(folder_id)
                primary_folder = folder_id
        elif action["type"] == "add_tag":
            tag = str(action["tag"])
            if tag not in current_tags:
                current_tags.append(tag)
    try:
        manual_filing.update_document_organization(
            document_id=document_id,
            payload=DocumentOrganizationWrite.model_validate(
                {
                    "folderIds": current_folders,
                    "primaryFolderId": primary_folder,
                    "tags": current_tags,
                }
            ),
            principal=principal,
        )
    except OrganizationError as exc:
        raise AutomationError(exc.status_code, exc.detail) from exc
    supported_actions = {"add_folder", "set_primary_folder", "add_tag"}
    return [dict(action) for action in actions if action["type"] in supported_actions]


def _evaluation_contract(
    rule: dict[str, Any],
    evaluation: RuleEvaluation,
    run: dict[str, Any] | None,
    *,
    status: str | None,
) -> FilingRuleEvaluation:
    payload = {
        "runId": run["id"] if run else None,
        "ruleId": rule["id"],
        "documentId": evaluation.document_id,
        "matched": evaluation.matched,
        "conditions": [condition.as_dict() for condition in evaluation.conditions],
        "proposedActions": evaluation.proposed_actions,
        "blockedActions": evaluation.blocked_actions,
        "appliedActions": run.get("applied_actions_json") if run else [],
        "reviewRequired": evaluation.review_required,
        "safetyReasons": evaluation.safety_reasons,
        "explanation": evaluation.explanation(),
    }
    if status is not None:
        payload["status"] = status
        return FilingRuleApplyResponse.model_validate(payload)
    return FilingRuleEvaluation.model_validate(payload)


def _rule_from_row(row: dict[str, Any]) -> FilingRule:
    return FilingRule.model_validate(
        {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description"),
            "enabled": row["enabled"],
            "priority": row.get("priority"),
            "reviewRequired": row.get("review_required"),
            "conditions": row.get("conditions_json") or [],
            "actions": row.get("actions_json") or [],
            "lastRunAt": row.get("last_run_at"),
        }
    )


def _suggestion_from_row(row: dict[str, Any]) -> FilingSuggestion:
    return FilingSuggestion.model_validate(
        {
            "runId": row["run_id"],
            "ruleId": row["rule_id"],
            "ruleName": row["rule_name"],
            "documentId": row["document_id"],
            "documentTitle": row["document_title"],
            "proposedActions": row.get("proposed_actions_json") or [],
            "blockedActions": row.get("blocked_actions_json") or [],
            "explanation": row.get("explanation_json") or {},
            "createdAt": row["created_at"],
        }
    )


def _access_context(principal: AuthPrincipal) -> DocumentAccessContext:
    household_id = _require_household(principal)
    return DocumentAccessContext(
        household_id=household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
    )


def _require_household(principal: AuthPrincipal) -> UUID:
    if not principal.household_id:
        raise AutomationError(403, "Household required")
    return principal.household_id


def _action_folder_id(action: dict[str, Any]) -> UUID | None:
    value = action.get("folder_id") or action.get("folderId")
    return _uuid(value) if value else None


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
