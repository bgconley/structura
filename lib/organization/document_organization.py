from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lib.auth import AuthPrincipal
from lib.contracts import DocumentOrganizationWrite
from lib.documents.access_policy import DocumentAccessContext
from lib.organization import policy, repository
from lib.search.projection import refresh_projection_and_enqueue_embedding


@dataclass(frozen=True)
class OrganizationMutationResult:
    document_id: UUID
    household_id: UUID
    changed_fields: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.changed_fields)


def update_document_organization_with_cursor(
    *,
    cur: object,
    document_id: UUID,
    payload: DocumentOrganizationWrite,
    principal: AuthPrincipal,
) -> OrganizationMutationResult:
    household_id = _require_household(principal)
    fields = payload.model_fields_set
    document = repository.lock_document_for_household(
        cur,
        document_id=document_id,
        access=document_access_context(principal),
    )
    if not document:
        raise policy.organization_error(404, "Document not found")
    before = repository.document_organization_snapshot(cur, document_id)

    repository.update_document_fields(
        cur,
        document_id=document_id,
        title=policy.normalize_document_title(payload.title) if "title" in fields else None,
        document_date=payload.document_date,
        filing_notes=(
            policy.normalize_optional_text(payload.filing_notes)
            if "filing_notes" in fields
            else None
        ),
        update_title="title" in fields,
        update_document_date="document_date" in fields,
        update_filing_notes="filing_notes" in fields,
    )

    folder_fields_present = bool({"folder_ids", "primary_folder_id"} & fields)
    if folder_fields_present:
        _update_document_folders(
            cur=cur,
            document_id=document_id,
            document=document,
            payload=payload,
            fields=fields,
            principal=principal,
            household_id=household_id,
        )

    if "tags" in fields:
        _update_document_tags(cur, document_id=document_id, tag_names=payload.tags or [])

    if fields and not folder_fields_present and "tags" not in fields:
        repository.touch_document(cur, document_id)
    elif "tags" in fields:
        repository.touch_document(cur, document_id)

    after = repository.document_organization_snapshot(cur, document_id)
    changed_fields = [
        field_name
        for field_name, before_value in before.items()
        if before_value != after.get(field_name)
    ]
    if changed_fields:
        repository.record_organization_audit(
            cur,
            document_id=document_id,
            actor_label=principal.email,
            before=before,
            after=after,
            changed_fields=changed_fields,
        )
    return OrganizationMutationResult(
        document_id=document_id,
        household_id=household_id,
        changed_fields=changed_fields,
    )


def refresh_document_organization_projection(result: OrganizationMutationResult) -> None:
    if not result.changed:
        return
    refresh_projection_and_enqueue_embedding(
        document_id=result.document_id,
        household_id=result.household_id,
        force_reembed=False,
    )


def document_access_context(principal: AuthPrincipal) -> DocumentAccessContext:
    household_id = _require_household(principal)
    return DocumentAccessContext(
        household_id=household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
    )


def _update_document_folders(
    *,
    cur: object,
    document_id: UUID,
    document: dict[str, object],
    payload: DocumentOrganizationWrite,
    fields: set[str],
    principal: AuthPrincipal,
    household_id: UUID,
) -> None:
    current_folder_ids = repository.document_folder_ids(cur, document_id)
    target_folder_ids = (
        policy.dedupe_uuids(payload.folder_ids or [])
        if "folder_ids" in fields
        else current_folder_ids
    )
    primary_folder_id = payload.primary_folder_id
    if "primary_folder_id" not in fields:
        primary_folder_id = _optional_uuid(document.get("primary_folder_id"))
    if primary_folder_id and primary_folder_id not in target_folder_ids:
        target_folder_ids.append(primary_folder_id)
    _validate_manual_folders(
        cur,
        folder_ids=target_folder_ids,
        principal=principal,
        household_id=household_id,
    )
    if target_folder_ids:
        if primary_folder_id not in target_folder_ids:
            primary_folder_id = target_folder_ids[0]
    else:
        primary_folder_id = None
    repository.replace_document_folders(
        cur,
        document_id=document_id,
        folder_ids=target_folder_ids,
        primary_folder_id=primary_folder_id,
    )


def _validate_manual_folders(
    cur: object,
    *,
    folder_ids: list[UUID],
    principal: AuthPrincipal,
    household_id: UUID,
) -> None:
    for folder_id in folder_ids:
        row = repository.get_writable_folder(
            cur,
            folder_id=folder_id,
            household_id=household_id,
            user_id=principal.user_id,
        )
        if not row or row["folder_kind"] != "manual":
            raise policy.organization_error(
                422,
                "Folder selection contains an unavailable manual folder",
            )


def _update_document_tags(cur: object, *, document_id: UUID, tag_names: list[str]) -> None:
    target_tag_names = policy.normalize_tag_names(tag_names)
    tag_rows = repository.resolve_tags_by_name(cur, target_tag_names)
    found = {str(row["name"]).casefold() for row in tag_rows}
    missing = [name for name in target_tag_names if name.casefold() not in found]
    if missing:
        raise policy.organization_error(422, f"Unknown tag: {missing[0]}")
    repository.replace_document_tags(
        cur,
        document_id=document_id,
        tag_ids=[_required_uuid(row["id"]) for row in tag_rows],
    )


def _require_household(principal: AuthPrincipal) -> UUID:
    if not principal.household_id:
        raise policy.organization_error(403, "Household required")
    return principal.household_id


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    return _required_uuid(value)


def _required_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
