from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.structura_api.dependencies import current_principal, require_csrf

router = APIRouter(prefix="/api/v1")


@router.get("/relationships", tags=["Relationships"])
def list_relationships(
    _principal: Annotated[object, Depends(current_principal)],
    documentId: UUID | None = None,
) -> dict[str, object]:
    return {"items": []}


@router.post(
    "/relationships",
    tags=["Relationships"],
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def create_relationship(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Document relationships are implemented in Phase 7.",
    )


@router.post("/analysis-notes", tags=["Analysis"], status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_analysis_note(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Analysis notes are implemented in Phase 9.",
    )


@router.post("/exports", tags=["Exports"], status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_export(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Exports are implemented in Phase 10.",
    )
