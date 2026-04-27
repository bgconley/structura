from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.structura_api.dependencies import require_csrf

router = APIRouter(prefix="/api/v1")


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
