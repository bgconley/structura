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
from lib.documents.read_model import get_document_detail
from lib.organization import policy, repository
from lib.organization.document_organization import (
    document_access_context,
    refresh_document_organization_projection,
    update_document_organization_with_cursor,
)


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
    with db_connection() as conn:
        with conn.cursor() as cur:
            result = update_document_organization_with_cursor(
                cur=cur,
                document_id=document_id,
                payload=payload,
                principal=principal,
            )
        conn.commit()
    refresh_document_organization_projection(result)

    detail = get_document_detail(document_id, document_access_context(principal))
    if not detail:
        raise policy.organization_error(404, "Document not found")
    return detail


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
