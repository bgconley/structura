from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.contracts import SavedSearch, SavedSearchWrite, SearchRequest, SearchResponse
from lib.documents.access_policy import DocumentAccessContext
from lib.search import SearchService
from lib.search.query import SearchValidationError
from lib.search.saved_searches import (
    SavedSearchError,
    create_saved_search,
    list_saved_searches,
)

router = APIRouter(prefix="/api/v1", tags=["Search"])


@router.post("/search", response_model=SearchResponse)
def post_search(
    payload: SearchRequest,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> SearchResponse:
    access = _access_context(principal)
    try:
        return SearchService().search(
            payload,
            access=access,
        )
    except SearchValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/saved-searches")
def get_saved_searches(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    access = _access_context(principal)
    return {"items": [item.model_dump(by_alias=True) for item in list_saved_searches(access)]}


@router.post(
    "/saved-searches",
    response_model=SavedSearch,
    status_code=status.HTTP_201_CREATED,
)
def post_saved_search(
    payload: SavedSearchWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> SavedSearch:
    access = _access_context(principal)
    try:
        return create_saved_search(payload, access=access, owner_user_id=principal.user_id)
    except SavedSearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _access_context(principal: AuthPrincipal) -> DocumentAccessContext:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")
    return DocumentAccessContext(
        household_id=principal.household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
    )
