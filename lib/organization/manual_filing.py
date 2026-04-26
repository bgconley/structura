from __future__ import annotations

from uuid import UUID

from psycopg.errors import UniqueViolation

from lib.auth import AuthPrincipal
from lib.contracts import (
    DocumentDetail,
    DocumentOrganizationWrite,
    Folder,
    FolderWrite,
    Tag,
    TagWrite,
)
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.documents.read_model import get_document_detail
from lib.organization import policy, repository


def list_folders(principal: AuthPrincipal) -> list[Folder]:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = repository.list_accessible_folders(
                cur,
                household_id=household_id,
                user_id=principal.user_id,
            )
    return [_folder_from_row(row) for row in rows]


def create_folder(payload: FolderWrite, principal: AuthPrincipal) -> Folder:
    household_id = _require_household(principal)
    name = policy.normalize_folder_name(payload.name)
    acl_mode = policy.validate_acl_mode(payload.acl_mode)
    saved_query = policy.validate_saved_query(payload.folder_kind, payload.saved_query)
    row: dict[str, object] | None = None

    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                parent_path: str | None = None
                if payload.parent_id:
                    parent = repository.get_writable_folder(
                        cur,
                        folder_id=payload.parent_id,
                        household_id=household_id,
                        user_id=principal.user_id,
                    )
                    if not parent:
                        raise policy.organization_error(404, "Parent folder not found")
                    parent_path = str(parent["path"])
                path = policy.folder_path(parent_path, name)
                if repository.folder_name_exists(
                    cur,
                    name=name,
                    parent_id=payload.parent_id,
                    household_id=household_id,
                ):
                    raise policy.organization_error(409, "Folder name already exists at this level")
                row = repository.insert_folder(
                    cur,
                    parent_id=payload.parent_id,
                    folder_kind=payload.folder_kind,
                    name=name,
                    description=payload.description,
                    path=path,
                    saved_query=saved_query,
                    household_id=household_id,
                    owner_user_id=principal.user_id,
                    acl_mode=acl_mode,
                    path_ltree=policy.ltree_from_path(path),
                )
            conn.commit()
    except UniqueViolation as exc:
        raise policy.organization_error(409, "Folder name already exists at this level") from exc
    if not row:
        raise policy.organization_error(500, "Failed to create folder")
    return _folder_from_row(row)


def list_tags(_principal: AuthPrincipal) -> list[Tag]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = repository.list_tags(cur)
    return [_tag_from_row(row) for row in rows]


def create_tag(payload: TagWrite, _principal: AuthPrincipal) -> Tag:
    name = policy.normalize_tag_name(payload.name)
    color_hex = policy.normalize_color_hex(payload.color_hex)
    with db_connection() as conn:
        with conn.cursor() as cur:
            if repository.tag_name_exists(cur, name):
                raise policy.organization_error(409, "Tag name already exists")
            row = repository.insert_tag(
                cur,
                name=name,
                color_hex=color_hex,
                description=payload.description,
            )
        conn.commit()
    if not row:
        raise policy.organization_error(500, "Failed to create tag")
    return _tag_from_row(row)


def update_document_organization(
    *,
    document_id: UUID,
    payload: DocumentOrganizationWrite,
    principal: AuthPrincipal,
) -> DocumentDetail:
    household_id = _require_household(principal)
    fields = payload.model_fields_set
    with db_connection() as conn:
        with conn.cursor() as cur:
            document = repository.lock_document_for_household(
                cur,
                document_id=document_id,
                access=_document_access_context(principal),
            )
            if not document:
                raise policy.organization_error(404, "Document not found")
            before = repository.document_organization_snapshot(cur, document_id)

            repository.update_document_fields(
                cur,
                document_id=document_id,
                title=(
                    policy.normalize_document_title(payload.title) if "title" in fields else None
                ),
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
        conn.commit()

    detail = get_document_detail(document_id, _document_access_context(principal))
    if not detail:
        raise policy.organization_error(404, "Document not found")
    return detail


def _document_access_context(principal: AuthPrincipal) -> DocumentAccessContext:
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


def _folder_from_row(row: dict[str, object]) -> Folder:
    saved_query = row.get("saved_query_json")
    return Folder.model_validate(
        {
            "id": row["id"],
            "parentId": row.get("parent_id"),
            "folderKind": row["folder_kind"],
            "name": row["name"],
            "path": row.get("path"),
            "savedQuery": saved_query if isinstance(saved_query, dict) else None,
            "aclMode": row.get("acl_mode"),
        }
    )


def _tag_from_row(row: dict[str, object]) -> Tag:
    return Tag.model_validate(
        {
            "id": row["id"],
            "name": row["name"],
            "colorHex": row.get("color_hex"),
            "description": row.get("description"),
        }
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
