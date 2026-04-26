from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.auth import AuthPrincipal
from lib.contacts import policy, repository
from lib.contracts import (
    Contact,
    ContactMergeSuggestion,
    ContactMergeWrite,
    ContactWrite,
    DocumentContact,
    DocumentContactWrite,
)
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.search.projection import refresh_projection_and_enqueue_embedding


def list_contacts(
    principal: AuthPrincipal,
    *,
    query: str | None = None,
    contact_type: str | None = None,
) -> list[Contact]:
    household_id = _require_household(principal)
    resolved_type = policy.normalize_contact_type(contact_type) if contact_type else None
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = repository.list_contacts(
                cur,
                household_id=household_id,
                query=query.strip() if query and query.strip() else None,
                contact_type=resolved_type,
            )
    return [_contact_from_row(row) for row in rows]


def upsert_contact(payload: ContactWrite, principal: AuthPrincipal) -> Contact:
    household_id = _require_household(principal)
    contact_type = policy.normalize_contact_type(payload.contact_type)
    display_name = policy.normalize_display_name(payload.display_name)
    normalized_name = policy.normalize_contact_name(display_name)
    aliases = policy.normalize_aliases(payload.aliases)
    with db_connection() as conn:
        with conn.cursor() as cur:
            if payload.id:
                row = repository.update_contact(
                    cur,
                    contact_id=payload.id,
                    household_id=household_id,
                    contact_type=contact_type,
                    display_name=display_name,
                    normalized_name=normalized_name,
                    identifiers=payload.identifiers,
                )
                if not row:
                    raise policy.contact_error(404, "Contact not found")
                event_name = "contact.updated"
            else:
                row = repository.insert_contact(
                    cur,
                    household_id=household_id,
                    contact_type=contact_type,
                    display_name=display_name,
                    normalized_name=normalized_name,
                    identifiers=payload.identifiers,
                )
                if not row:
                    raise policy.contact_error(500, "Contact was not created")
                event_name = "contact.created"
            contact_id = _required_uuid(row["id"])
            repository.replace_aliases(cur, contact_id=contact_id, aliases=aliases)
            repository.record_contact_audit(
                cur,
                event_name=event_name,
                contact_id=contact_id,
                actor_label=principal.email,
                payload={"aliases": aliases, "identifiers": payload.identifiers},
            )
        conn.commit()
    refreshed = list_contacts(principal, query=display_name)
    return next(contact for contact in refreshed if contact.id == contact_id)


def link_document_contact(
    *,
    document_id: UUID,
    payload: DocumentContactWrite,
    principal: AuthPrincipal,
) -> DocumentContact:
    household_id = _require_household(principal)
    role_name = policy.normalize_display_name(payload.role_name)
    with db_connection() as conn:
        with conn.cursor() as cur:
            document = repository.lock_writable_document(
                cur,
                document_id=document_id,
                access=_access_context(principal),
            )
            if not document:
                raise policy.contact_error(404, "Document not found")
            contact = repository.get_contact(
                cur,
                contact_id=payload.contact_id,
                household_id=household_id,
            )
            if not contact:
                raise policy.contact_error(404, "Contact not found")
            row = repository.upsert_document_contact(
                cur,
                document_id=document_id,
                contact_id=payload.contact_id,
                role_name=role_name,
                evidence=payload.evidence,
                confidence=payload.confidence,
            )
            if not row:
                raise policy.contact_error(500, "Document contact was not saved")
            repository.record_contact_audit(
                cur,
                event_name="document_contact.linked",
                contact_id=payload.contact_id,
                actor_label=principal.email,
                payload={"documentId": str(document_id), "roleName": role_name},
            )
        conn.commit()
    refresh_projection_and_enqueue_embedding(
        document_id=document_id,
        household_id=household_id,
        force_reembed=False,
    )
    return _document_contact_from_row({**row, "display_name": contact["display_name"]})


def list_document_contacts(document_id: UUID, principal: AuthPrincipal) -> list[DocumentContact]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = repository.list_document_contacts(
                cur,
                document_id=document_id,
                access=_access_context(principal),
            )
    return [_document_contact_from_row(row) for row in rows]


def list_merge_suggestions(principal: AuthPrincipal) -> list[ContactMergeSuggestion]:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = repository.merge_suggestions(cur, household_id=household_id)
    return [ContactMergeSuggestion.model_validate(row) for row in rows]


def merge_contacts(
    *,
    source_contact_id: UUID,
    payload: ContactMergeWrite,
    principal: AuthPrincipal,
) -> Contact:
    household_id = _require_household(principal)
    if source_contact_id == payload.target_contact_id:
        raise policy.contact_error(422, "Cannot merge a contact into itself")
    with db_connection() as conn:
        with conn.cursor() as cur:
            row = repository.merge_contacts(
                cur,
                source_contact_id=source_contact_id,
                target_contact_id=payload.target_contact_id,
                household_id=household_id,
            )
            if not row:
                raise policy.contact_error(404, "Contact not found")
            repository.record_contact_audit(
                cur,
                event_name="contact.merged",
                contact_id=payload.target_contact_id,
                actor_label=principal.email,
                payload={
                    "sourceContactId": str(source_contact_id),
                    "targetContactId": str(payload.target_contact_id),
                },
            )
        conn.commit()
    refreshed = list_contacts(principal, query=str(row["display_name"]))
    return next(contact for contact in refreshed if contact.id == payload.target_contact_id)


def _access_context(principal: AuthPrincipal) -> DocumentAccessContext:
    household_id = _require_household(principal)
    return DocumentAccessContext(
        household_id=household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
    )


def _require_household(principal: AuthPrincipal) -> UUID:
    if not principal.household_id:
        raise policy.contact_error(403, "Household required")
    return principal.household_id


def _contact_from_row(row: dict[str, Any]) -> Contact:
    return Contact.model_validate(
        {
            "id": row["id"],
            "contactType": row["contact_type"],
            "displayName": row["display_name"],
            "normalizedName": row.get("normalized_name"),
            "aliases": list(row.get("aliases") or []),
            "identifiers": row.get("identifiers_json") or {},
            "linkedDocumentCount": row.get("linked_document_count") or 0,
        }
    )


def _document_contact_from_row(row: dict[str, Any]) -> DocumentContact:
    return DocumentContact.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "contactId": row["contact_id"],
            "displayName": row["display_name"],
            "roleName": row["role_name"],
            "evidence": row.get("evidence_json") or {},
            "confidence": row.get("confidence"),
        }
    )


def _required_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
