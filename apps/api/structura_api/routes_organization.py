from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.contracts import (
    DocumentDetail,
    DocumentOrganizationWrite,
    Folder,
    FolderWrite,
    Tag,
    TagWrite,
)
from lib.organization import manual_filing
from lib.organization.policy import OrganizationError

router = APIRouter(prefix="/api/v1", tags=["Organization"])
T = TypeVar("T")


@router.get("/folders", tags=["Organization"])
def list_folders(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    return {
        "items": [
            folder.model_dump(by_alias=True)
            for folder in _call_organization(lambda: manual_filing.list_folders(principal))
        ]
    }


@router.post(
    "/folders",
    tags=["Organization"],
    response_model=Folder,
    status_code=status.HTTP_201_CREATED,
)
def create_folder(
    payload: FolderWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> Folder:
    return _call_organization(lambda: manual_filing.create_folder(payload, principal))


@router.get("/tags", tags=["Organization"])
def list_tags(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    return {
        "items": [
            tag.model_dump(by_alias=True)
            for tag in _call_organization(lambda: manual_filing.list_tags(principal))
        ]
    }


@router.post(
    "/tags",
    tags=["Organization"],
    response_model=Tag,
    status_code=status.HTTP_201_CREATED,
)
def create_tag(
    payload: TagWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> Tag:
    return _call_organization(lambda: manual_filing.create_tag(payload, principal))


@router.post(
    "/documents/{documentId}/organization",
    tags=["Organization"],
    response_model=DocumentDetail,
)
def update_document_organization(
    documentId: UUID,
    payload: DocumentOrganizationWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> DocumentDetail:
    return _call_organization(
        lambda: manual_filing.update_document_organization(
            document_id=documentId,
            payload=payload,
            principal=principal,
        )
    )


def _call_organization(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except OrganizationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
