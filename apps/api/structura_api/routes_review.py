from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.contracts import CanonicalFieldWrite, ReviewActionRequest
from lib.documents.access_policy import DocumentAccessContext
from lib.review import ReviewService
from lib.review.repository import (
    ReviewRepositoryError,
    list_canonical_fields,
    list_field_candidates,
    list_review_tasks,
)
from lib.review.service import ReviewServiceError

router = APIRouter(prefix="/api/v1", tags=["Review"])


@router.get("/review-tasks")
def get_review_tasks(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, object]:
    access = _access_context(principal)
    items = list_review_tasks(access=access, status=status_filter, limit=limit)
    return {"items": [item.model_dump(by_alias=True) for item in items]}


@router.get("/documents/{documentId}/field-candidates")
def get_field_candidates(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    fieldPath: str | None = None,
) -> dict[str, object]:
    access = _access_context(principal)
    try:
        items = list_field_candidates(
            document_id=documentId,
            access=access,
            field_path=fieldPath,
        )
    except ReviewRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc
    return {"items": [item.model_dump(by_alias=True) for item in items]}


@router.get("/documents/{documentId}/canonical-fields")
def get_canonical_fields(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    access = _access_context(principal)
    try:
        items = list_canonical_fields(document_id=documentId, access=access)
    except ReviewRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc
    return {"items": [item.model_dump(by_alias=True) for item in items]}


@router.post("/documents/{documentId}/canonical-fields")
def post_canonical_field(
    documentId: UUID,
    payload: CanonicalFieldWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> dict[str, object]:
    access = _access_context(principal)
    service = ReviewService()
    try:
        field = service.write_canonical_field(
            documentId,
            payload,
            access=access,
            actor_user_id=principal.user_id,
        )
    except (ReviewRepositoryError, ReviewServiceError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return field.model_dump(by_alias=True)


@router.post("/documents/{documentId}/review-actions")
def post_review_action(
    documentId: UUID,
    payload: ReviewActionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> dict[str, object]:
    if payload.document_id != documentId:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="documentId mismatch"
        )
    access = _access_context(principal)
    try:
        result = ReviewService().apply_review_action(
            payload,
            access=access,
            actor_user_id=principal.user_id,
        )
    except (ReviewRepositoryError, ReviewServiceError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return result


def _access_context(principal: AuthPrincipal) -> DocumentAccessContext:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")
    return DocumentAccessContext(
        household_id=principal.household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
    )
