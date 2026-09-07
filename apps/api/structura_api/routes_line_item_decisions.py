"""Thin authenticated routes for explicit canonical line selection and history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.structura_api.dependencies import require_document_read, require_document_review
from lib.auth import AuthPrincipal
from lib.auth.request_authority import RequestCredential
from lib.contracts.line_item_authority import (
    CanonicalLineResponse,
    LineDecisionRequest,
    LineDecisionResponse,
    LineHistoryResponse,
)
from lib.review.errors import ReviewRepositoryError
from lib.review.line_items.errors import LineDecisionConflict, LineEvidenceError
from lib.review.line_items.history_read import line_history
from lib.review.line_items.read_repository import canonical_lines
from lib.review.line_items.service import decide_line

router = APIRouter(prefix="/api/v1", tags=["Review"])


@router.get("/documents/{documentId}/canonical-line-items", response_model=CanonicalLineResponse)
def get_canonical_lines(
    documentId: UUID, principal: Annotated[AuthPrincipal, Depends(require_document_read)]
) -> CanonicalLineResponse:
    try:
        return canonical_lines(
            document_id=documentId, credential=RequestCredential.from_principal(principal)
        )
    except ReviewRepositoryError:
        raise HTTPException(status_code=404, detail="Document not found") from None


@router.post("/documents/{documentId}/line-item-decisions", response_model=LineDecisionResponse)
def post_line_decision(
    documentId: UUID,
    request: LineDecisionRequest,
    principal: Annotated[AuthPrincipal, Depends(require_document_review)],
) -> LineDecisionResponse:
    try:
        return decide_line(
            document_id=documentId,
            credential=RequestCredential.from_principal(principal),
            request=request,
        )
    except ReviewRepositoryError:
        raise HTTPException(status_code=404, detail="Document not found") from None
    except LineDecisionConflict:
        raise HTTPException(
            status_code=409,
            detail="This line item changed or requires an explicit target. "
            "Reload it before saving your decision.",
        ) from None
    except LineEvidenceError:
        raise HTTPException(
            status_code=422,
            detail="This line item requires complete source evidence before publication.",
        ) from None


@router.get("/documents/{documentId}/line-item-history", response_model=LineHistoryResponse)
def get_line_history(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
    canonicalLineItemId: UUID | None = None,
    sourceCandidateId: UUID | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LineHistoryResponse:
    try:
        return line_history(
            document_id=documentId,
            credential=RequestCredential.from_principal(principal),
            canonical_line_item_id=canonicalLineItemId,
            source_candidate_id=sourceCandidateId,
            cursor=cursor,
            limit=limit,
        )
    except ReviewRepositoryError:
        raise HTTPException(status_code=404, detail="Document not found") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid line history request.") from None
