from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.automation import service as automation_service
from lib.automation import watched_folders as watched_folder_service
from lib.automation.errors import AutomationError
from lib.contracts import (
    FilingRule,
    FilingRuleApplyRequest,
    FilingRuleApplyResponse,
    FilingRuleDryRunRequest,
    FilingRuleDryRunResponse,
    FilingRuleWrite,
    WatchedFolder,
    WatchedFolderWrite,
)

router = APIRouter(prefix="/api/v1", tags=["Automation"])
T = TypeVar("T")


@router.get("/filing-rules")
def list_filing_rules(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    rules = _call_automation(lambda: automation_service.list_filing_rules(principal))
    return {"items": [rule.model_dump(by_alias=True) for rule in rules]}


@router.post(
    "/filing-rules",
    response_model=FilingRule,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"description": "CSRF token required"}},
)
def upsert_filing_rule(
    payload: FilingRuleWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> FilingRule:
    return _call_automation(lambda: automation_service.upsert_filing_rule(payload, principal))


@router.post(
    "/filing-rules/{ruleId}/dry-run",
    response_model=FilingRuleDryRunResponse,
    responses={
        403: {"description": "CSRF token required"},
        404: {"description": "Filing rule not found"},
    },
)
def dry_run_filing_rule(
    ruleId: UUID,
    payload: FilingRuleDryRunRequest,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> FilingRuleDryRunResponse:
    return _call_automation(
        lambda: automation_service.dry_run_rule(
            rule_id=ruleId,
            payload=payload,
            principal=principal,
        )
    )


@router.post(
    "/filing-rules/{ruleId}/apply",
    response_model=FilingRuleApplyResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        403: {"description": "CSRF token required"},
        404: {"description": "Filing rule or document not found"},
    },
)
def apply_filing_rule(
    ruleId: UUID,
    payload: FilingRuleApplyRequest,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> FilingRuleApplyResponse:
    return _call_automation(
        lambda: automation_service.apply_rule(
            rule_id=ruleId,
            payload=payload,
            principal=principal,
        )
    )


@router.get("/filing-suggestions")
def list_filing_suggestions(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    suggestions = _call_automation(lambda: automation_service.list_filing_suggestions(principal))
    return {"items": [suggestion.model_dump(by_alias=True) for suggestion in suggestions]}


@router.post(
    "/filing-suggestions/{runId}/accept",
    response_model=FilingRuleApplyResponse,
    responses={
        403: {"description": "CSRF token required"},
        404: {"description": "Filing suggestion not found"},
    },
)
def accept_filing_suggestion(
    runId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> FilingRuleApplyResponse:
    return _call_automation(
        lambda: automation_service.accept_suggestion(run_id=runId, principal=principal)
    )


@router.post(
    "/filing-suggestions/{runId}/reject",
    responses={
        403: {"description": "CSRF token required"},
        404: {"description": "Filing suggestion not found"},
    },
)
def reject_filing_suggestion(
    runId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> dict[str, bool]:
    return _call_automation(
        lambda: automation_service.reject_suggestion(run_id=runId, principal=principal)
    )


@router.post(
    "/filing-suggestions/{runId}/defer",
    responses={
        403: {"description": "CSRF token required"},
        404: {"description": "Filing suggestion not found"},
    },
)
def defer_filing_suggestion(
    runId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> dict[str, bool]:
    return _call_automation(
        lambda: automation_service.defer_suggestion(run_id=runId, principal=principal)
    )


@router.get("/watched-folders")
def list_watched_folders(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    watched = _call_automation(lambda: watched_folder_service.list_watched_folders(principal))
    return {"items": [item.model_dump(by_alias=True) for item in watched]}


@router.post(
    "/watched-folders",
    response_model=WatchedFolder,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"description": "CSRF token required"}},
)
def upsert_watched_folder(
    payload: WatchedFolderWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> WatchedFolder:
    return _call_automation(
        lambda: watched_folder_service.upsert_watched_folder(payload, principal)
    )


@router.get("/import-status")
def list_import_status(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    statuses = _call_automation(lambda: watched_folder_service.list_import_status(principal))
    return {"items": [item.model_dump(by_alias=True) for item in statuses]}


def _call_automation(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except AutomationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
