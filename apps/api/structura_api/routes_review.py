from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.structura_api.dependencies import require_document_read, require_document_review
from lib.auth import AuthPrincipal
from lib.auth.request_authority import RequestCredential
from lib.contracts import CanonicalFieldWrite, ReviewActionRequest, ReviewTask
from lib.documents.access_policy import DocumentAccessContext
from lib.fact_authority.preconditions import AuthorityRevisionConflict
from lib.review import ReviewService
from lib.review.correction_revision import CorrectionConflictError
from lib.review.correction_values import CorrectionValueError
from lib.review.line_items.read_repository import candidate_lines
from lib.review.repository import (
    ReviewRepositoryError,
    get_canonical_field_response,
    get_review_task,
    list_field_candidates,
    list_observation_candidates,
    list_review_tasks,
)
from lib.review.service import ReviewServiceError

router = APIRouter(prefix="/api/v1", tags=["Review"])


@router.get("/review-tasks")
def get_review_tasks(
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    document_id: Annotated[UUID | None, Query(alias="documentId")] = None,
) -> dict[str, object]:
    access = _access_context(principal)
    items = list_review_tasks(
        access=access, status=status_filter, limit=limit, document_id=document_id
    )
    return {"items": [item.model_dump(by_alias=True) for item in items]}


@router.get("/review-tasks/{reviewTaskId}", response_model=ReviewTask)
def get_review_task_detail(
    reviewTaskId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
) -> ReviewTask:
    task = get_review_task(review_task_id=reviewTaskId, access=_access_context(principal))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return task


@router.get("/documents/{documentId}/field-candidates")
def get_field_candidates(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
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


@router.get("/documents/{documentId}/observation-candidates")
def get_observation_candidates(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
    observationId: UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> dict[str, object]:
    access = _access_context(principal)
    try:
        items = list_observation_candidates(
            document_id=documentId,
            access=access,
            observation_id=observationId,
            status=status_filter,
        )
    except ReviewRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc
    return {"items": [item.model_dump(by_alias=True) for item in items]}


@router.get("/documents/{documentId}/line-item-candidates")
def get_line_item_candidates(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
    candidateId: UUID | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> dict[str, object]:
    try:
        return candidate_lines(
            document_id=documentId,
            credential=RequestCredential.from_principal(principal),
            candidate_id=candidateId,
            status=status_filter,
        )
    except ReviewRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc


@router.get("/documents/{documentId}/canonical-fields")
def get_canonical_fields(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
) -> dict[str, object]:
    access = _access_context(principal)
    try:
        response = get_canonical_field_response(document_id=documentId, access=access)
    except ReviewRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        ) from exc
    return response.model_dump(by_alias=True)


@router.post("/documents/{documentId}/canonical-fields")
def post_canonical_field(
    documentId: UUID,
    payload: CanonicalFieldWrite,
    principal: Annotated[AuthPrincipal, Depends(require_document_review)],
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
    except AuthorityRevisionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "This field changed since it was loaded. Reload it before saving your decision."
            ),
        ) from exc
    except CorrectionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CorrectionValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ReviewRepositoryError, ReviewServiceError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return field.model_dump(by_alias=True)


@router.post("/documents/{documentId}/review-actions")
def post_review_action(
    documentId: UUID,
    payload: ReviewActionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_document_review)],
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
    except AuthorityRevisionConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "This field changed since it was loaded. Reload it before saving your decision."
            ),
        ) from exc
    except CorrectionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CorrectionValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
        api_token_id=principal.api_token_id,
        scopes=principal.scopes,
    )
