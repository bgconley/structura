from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.structura_api.dependencies import require_admin
from lib.auth import AuthPrincipal
from lib.documents.parse_debug import ParseDebugLimits, get_parse_debug_view

router = APIRouter(prefix="/api/v1", tags=["Documents"])


@router.get("/documents/{documentId}/parse-debug")
def get_document_parse_debug(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_admin)],
    pageLimit: Annotated[int, Query(ge=1, le=200)] = 50,
    elementLimit: Annotated[int, Query(ge=1, le=500)] = 100,
    tableLimit: Annotated[int, Query(ge=1, le=200)] = 50,
    chunkLimit: Annotated[int, Query(ge=1, le=500)] = 100,
    jobLimit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, object]:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    debug = get_parse_debug_view(
        document_id=documentId,
        household_id=principal.household_id,
        limits=ParseDebugLimits(
            page_limit=pageLimit,
            element_limit=elementLimit,
            table_limit=tableLimit,
            chunk_limit=chunkLimit,
            job_limit=jobLimit,
        ),
    )
    if not debug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return debug
