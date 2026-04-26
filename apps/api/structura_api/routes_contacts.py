from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.contacts import service as contact_service
from lib.contacts.policy import ContactError
from lib.contracts import (
    Contact,
    ContactMergeWrite,
    ContactWrite,
    DocumentContact,
    DocumentContactWrite,
)

router = APIRouter(prefix="/api/v1", tags=["Organization"])
T = TypeVar("T")


@router.get("/contacts", response_model=dict[str, list[Contact]])
def list_contacts(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    q: str | None = None,
    contactType: str | None = None,
) -> dict[str, object]:
    contacts = _call_contacts(
        lambda: contact_service.list_contacts(
            principal,
            query=q,
            contact_type=contactType,
        )
    )
    return {"items": [contact.model_dump(by_alias=True) for contact in contacts]}


@router.post(
    "/contacts",
    response_model=Contact,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"description": "CSRF token required"}},
)
def upsert_contact(
    payload: ContactWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> Contact:
    return _call_contacts(lambda: contact_service.upsert_contact(payload, principal))


@router.get("/contact-merge-suggestions")
def list_contact_merge_suggestions(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    suggestions = _call_contacts(lambda: contact_service.list_merge_suggestions(principal))
    return {"items": [item.model_dump(by_alias=True) for item in suggestions]}


@router.post(
    "/contacts/{contactId}/merge",
    response_model=Contact,
    responses={
        403: {"description": "CSRF token required"},
        404: {"description": "Contact not found"},
    },
)
def merge_contact(
    contactId: UUID,
    payload: ContactMergeWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> Contact:
    return _call_contacts(
        lambda: contact_service.merge_contacts(
            source_contact_id=contactId,
            payload=payload,
            principal=principal,
        )
    )


@router.get("/documents/{documentId}/contacts")
def list_document_contacts(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    links = _call_contacts(lambda: contact_service.list_document_contacts(documentId, principal))
    return {"items": [link.model_dump(by_alias=True) for link in links]}


@router.post(
    "/documents/{documentId}/contacts",
    response_model=DocumentContact,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "CSRF token required"},
        404: {"description": "Document or contact not found"},
    },
)
def link_document_contact(
    documentId: UUID,
    payload: DocumentContactWrite,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> DocumentContact:
    return _call_contacts(
        lambda: contact_service.link_document_contact(
            document_id=documentId,
            payload=payload,
            principal=principal,
        )
    )


def _call_contacts(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ContactError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
