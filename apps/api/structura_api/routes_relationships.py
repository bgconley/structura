from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.contracts import RelationshipDecisionRequest, RelationshipWrite
from lib.documents.access_policy import DocumentAccessContext
from lib.relationships.errors import RelationshipServiceError
from lib.relationships.service import RelationshipService

router = APIRouter(prefix="/api/v1", tags=["Relationships"])


@router.get(
    "/relationships",
    responses={401: {"description": "Not authenticated"}},
)
def list_relationships(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    documentId: UUID | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> dict[str, object]:
    items = RelationshipService().list_relationships(
        access=_access_context(principal),
        document_id=documentId,
        status=status,
        limit=limit,
    )
    return {"items": [item.model_dump(by_alias=True) for item in items]}


@router.post(
    "/relationships",
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "CSRF token required"},
        404: {"description": "Document not found"},
    },
)
def create_relationship(
    payload: RelationshipWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> dict[str, object]:
    try:
        item = RelationshipService().create_relationship(
            payload,
            access=_access_context(principal),
            actor_user_id=principal.user_id,
        )
    except RelationshipServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return item.model_dump(by_alias=True)


@router.post(
    "/relationships/{relationshipId}/accept",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "CSRF token required"},
        404: {"description": "Relationship not found"},
    },
)
def accept_relationship(
    relationshipId: UUID,
    payload: RelationshipDecisionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> dict[str, object]:
    try:
        item = RelationshipService().accept_relationship(
            relationshipId,
            payload,
            access=_access_context(principal),
            actor_user_id=principal.user_id,
        )
    except RelationshipServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return item.model_dump(by_alias=True)


@router.post(
    "/relationships/{relationshipId}/reject",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "CSRF token required"},
        404: {"description": "Relationship not found"},
    },
)
def reject_relationship(
    relationshipId: UUID,
    payload: RelationshipDecisionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> dict[str, object]:
    try:
        item = RelationshipService().reject_relationship(
            relationshipId,
            payload,
            access=_access_context(principal),
            actor_user_id=principal.user_id,
        )
    except RelationshipServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return item.model_dump(by_alias=True)


@router.get(
    "/deadlines",
    responses={401: {"description": "Not authenticated"}},
)
def list_deadlines(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    documentId: UUID | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> dict[str, object]:
    items = RelationshipService().list_deadlines(
        access=_access_context(principal),
        document_id=documentId,
        status=status,
        limit=limit,
    )
    return {"items": [item.model_dump(by_alias=True) for item in items]}


@router.get(
    "/timeline",
    responses={401: {"description": "Not authenticated"}},
)
def get_timeline(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    documentId: UUID | None = None,
    contactId: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> dict[str, object]:
    items = RelationshipService().timeline(
        access=_access_context(principal),
        document_id=documentId,
        contact_id=contactId,
        limit=limit,
    )
    return {"items": [item.model_dump(by_alias=True) for item in items]}


@router.get(
    "/smart-views",
    responses={401: {"description": "Not authenticated"}},
)
def list_smart_views(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    items = RelationshipService().smart_views(access=_access_context(principal))
    return {"items": [item.model_dump(by_alias=True) for item in items]}


def _access_context(principal: AuthPrincipal) -> DocumentAccessContext:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")
    return DocumentAccessContext(
        household_id=principal.household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
    )
