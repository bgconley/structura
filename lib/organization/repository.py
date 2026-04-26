from __future__ import annotations

from datetime import date
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
)


def list_accessible_folders(
    cur: Any,
    *,
    household_id: UUID,
    user_id: UUID,
) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT
          f.id,
          f.parent_id,
          f.folder_kind::text AS folder_kind,
          f.name,
          COALESCE(f.path_cache, '/' || f.name) AS path,
          f.saved_query_json,
          f.acl_mode
        FROM folders f
        WHERE (f.household_id = %s OR (f.household_id IS NULL AND f.is_system))
          AND (
            f.acl_mode = 'household'
            OR f.owner_user_id = %s
            OR EXISTS (
              SELECT 1
              FROM folder_acl fa
              WHERE fa.folder_id = f.id
                AND fa.permission IN ('read', 'write', 'admin')
                AND (
                  (fa.principal_type = 'user' AND fa.principal_id = %s)
                  OR (fa.principal_type = 'household' AND fa.principal_id = %s)
                )
            )
          )
        ORDER BY f.folder_kind::text, COALESCE(f.path_cache, '/' || f.name), lower(f.name)
        """,
        (household_id, user_id, user_id, household_id),
    )
    return cast(list[dict[str, object]], cur.fetchall())


def get_writable_folder(
    cur: Any,
    *,
    folder_id: UUID,
    household_id: UUID,
    user_id: UUID,
) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT
          f.id,
          f.parent_id,
          f.folder_kind::text AS folder_kind,
          f.name,
          COALESCE(f.path_cache, '/' || f.name) AS path,
          f.saved_query_json,
          f.acl_mode
        FROM folders f
        WHERE f.id = %s
          AND (f.household_id = %s OR (f.household_id IS NULL AND f.is_system))
          AND (
            f.acl_mode = 'household'
            OR f.owner_user_id = %s
            OR EXISTS (
              SELECT 1
              FROM folder_acl fa
              WHERE fa.folder_id = f.id
                AND fa.permission IN ('write', 'admin')
                AND (
                  (fa.principal_type = 'user' AND fa.principal_id = %s)
                  OR (fa.principal_type = 'household' AND fa.principal_id = %s)
                )
            )
          )
        """,
        (folder_id, household_id, user_id, user_id, household_id),
    )
    return cast(dict[str, object] | None, cur.fetchone())


def folder_name_exists(
    cur: Any,
    *,
    name: str,
    parent_id: UUID | None,
    household_id: UUID,
) -> bool:
    cur.execute(
        """
        SELECT id
        FROM folders
        WHERE lower(name) = lower(%s)
          AND COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid)
            = COALESCE(%s, '00000000-0000-0000-0000-000000000000'::uuid)
          AND (household_id = %s OR household_id IS NULL)
        LIMIT 1
        """,
        (name, parent_id, household_id),
    )
    return cur.fetchone() is not None


def insert_folder(
    cur: Any,
    *,
    parent_id: UUID | None,
    folder_kind: str,
    name: str,
    description: str | None,
    path: str,
    saved_query: dict[str, object] | None,
    household_id: UUID,
    owner_user_id: UUID,
    acl_mode: str,
    path_ltree: str,
) -> dict[str, object] | None:
    cur.execute(
        """
        INSERT INTO folders
          (
            parent_id,
            folder_kind,
            name,
            description,
            path_cache,
            saved_query_json,
            household_id,
            owner_user_id,
            acl_mode,
            path_ltree
          )
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, text2ltree(%s))
        RETURNING
          id,
          parent_id,
          folder_kind::text AS folder_kind,
          name,
          path_cache AS path,
          saved_query_json,
          acl_mode
        """,
        (
            parent_id,
            folder_kind,
            name,
            description,
            path,
            Jsonb(saved_query) if saved_query is not None else None,
            household_id,
            owner_user_id,
            acl_mode,
            path_ltree,
        ),
    )
    return cast(dict[str, object] | None, cur.fetchone())


def list_tags(cur: Any) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, name::text AS name, color_hex, description
        FROM tags
        ORDER BY is_system DESC, lower(name::text), id
        """,
    )
    return cast(list[dict[str, object]], cur.fetchall())


def tag_name_exists(cur: Any, name: str) -> bool:
    cur.execute(
        "SELECT id FROM tags WHERE lower(name::text) = lower(%s) LIMIT 1",
        (name,),
    )
    return cur.fetchone() is not None


def insert_tag(
    cur: Any,
    *,
    name: str,
    color_hex: str | None,
    description: str | None,
) -> dict[str, object] | None:
    cur.execute(
        """
        INSERT INTO tags (name, color_hex, description)
        VALUES (%s, %s, %s)
        RETURNING id, name::text AS name, color_hex, description
        """,
        (name, color_hex, description),
    )
    return cast(dict[str, object] | None, cur.fetchone())


def lock_document_for_household(
    cur: Any,
    *,
    document_id: UUID,
    access: DocumentAccessContext,
) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT id, primary_folder_id
        FROM documents d
        WHERE d.id = %s
          AND deleted_at IS NULL
          AND document_is_readable(d.id, %s, %s, %s)
        FOR UPDATE
        """,
        (document_id, *document_read_access_params(access)),
    )
    return cast(dict[str, object] | None, cur.fetchone())


def update_document_fields(
    cur: Any,
    *,
    document_id: UUID,
    title: str | None = None,
    document_date: date | None = None,
    filing_notes: str | None = None,
    update_title: bool = False,
    update_document_date: bool = False,
    update_filing_notes: bool = False,
) -> None:
    if update_title:
        cur.execute(
            "UPDATE documents SET title = %s, updated_at = now() WHERE id = %s",
            (title, document_id),
        )
    if update_document_date:
        cur.execute(
            "UPDATE documents SET document_date = %s, updated_at = now() WHERE id = %s",
            (document_date, document_id),
        )
    if update_filing_notes:
        cur.execute(
            "UPDATE documents SET filing_notes = %s, updated_at = now() WHERE id = %s",
            (filing_notes, document_id),
        )


def document_folder_ids(cur: Any, document_id: UUID) -> list[UUID]:
    cur.execute(
        """
        SELECT folder_id
        FROM document_folder_memberships
        WHERE document_id = %s
        ORDER BY created_at, folder_id
        """,
        (document_id,),
    )
    return [row["folder_id"] for row in cur.fetchall()]


def replace_document_folders(
    cur: Any,
    *,
    document_id: UUID,
    folder_ids: list[UUID],
    primary_folder_id: UUID | None,
) -> None:
    cur.execute("DELETE FROM document_folder_memberships WHERE document_id = %s", (document_id,))
    for folder_id in folder_ids:
        cur.execute(
            """
            INSERT INTO document_folder_memberships (document_id, folder_id, is_primary)
            VALUES (%s, %s, %s)
            """,
            (document_id, folder_id, folder_id == primary_folder_id),
        )
    cur.execute(
        """
        UPDATE documents
        SET primary_folder_id = %s,
            filed_at = CASE
              WHEN %s THEN COALESCE(filed_at, now())
              ELSE filed_at
            END,
            updated_at = now()
        WHERE id = %s
        """,
        (primary_folder_id, bool(folder_ids), document_id),
    )


def resolve_tags_by_name(cur: Any, tag_names: list[str]) -> list[dict[str, object]]:
    resolved: list[dict[str, object]] = []
    for name in tag_names:
        cur.execute(
            """
            SELECT id, name::text AS name
            FROM tags
            WHERE lower(name::text) = lower(%s)
            LIMIT 1
            """,
            (name,),
        )
        row = cur.fetchone()
        if row:
            resolved.append(row)
    return resolved


def replace_document_tags(cur: Any, *, document_id: UUID, tag_ids: list[UUID]) -> None:
    cur.execute("DELETE FROM document_tags WHERE document_id = %s", (document_id,))
    for tag_id in tag_ids:
        cur.execute(
            """
            INSERT INTO document_tags (document_id, tag_id)
            VALUES (%s, %s)
            """,
            (document_id, tag_id),
        )


def touch_document(cur: Any, document_id: UUID) -> None:
    cur.execute("UPDATE documents SET updated_at = now() WHERE id = %s", (document_id,))


def document_organization_snapshot(cur: Any, document_id: UUID) -> dict[str, object]:
    cur.execute(
        """
        SELECT
          d.title,
          d.document_date,
          d.filing_notes,
          d.primary_folder_id,
          COALESCE(
            (
              SELECT array_agg(dfm.folder_id ORDER BY dfm.created_at, dfm.folder_id)
              FROM document_folder_memberships dfm
              WHERE dfm.document_id = d.id
            ),
            ARRAY[]::uuid[]
          ) AS folder_ids,
          COALESCE(
            (
              SELECT array_agg(t.name::text ORDER BY lower(t.name::text), t.id)
              FROM document_tags dt
              JOIN tags t ON t.id = dt.tag_id
              WHERE dt.document_id = d.id
            ),
            ARRAY[]::text[]
          ) AS tags
        FROM documents d
        WHERE d.id = %s
        """,
        (document_id,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    document_date_value = row.get("document_date")
    return {
        "title": row["title"],
        "documentDate": document_date_value.isoformat() if document_date_value else None,
        "filingNotes": row.get("filing_notes"),
        "primaryFolderId": str(row["primary_folder_id"]) if row.get("primary_folder_id") else None,
        "folderIds": [str(value) for value in _uuid_list(row.get("folder_ids"))],
        "tags": _string_list(row.get("tags")),
    }


def record_organization_audit(
    cur: Any,
    *,
    document_id: UUID,
    actor_label: str,
    before: dict[str, object],
    after: dict[str, object],
    changed_fields: list[str],
) -> None:
    cur.execute(
        """
        INSERT INTO audit_events
          (entity_type, entity_id, document_id, event_name, actor_label, payload_json)
        VALUES ('document', %s, %s, 'document.organization_updated', %s, %s::jsonb)
        """,
        (
            document_id,
            document_id,
            actor_label,
            Jsonb(
                {
                    "schema_name": "document_organization_audit",
                    "schema_version": "v1",
                    "changed_fields": changed_fields,
                    "before": before,
                    "after": after,
                }
            ),
        ),
    )


def _uuid_list(value: object) -> list[UUID]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item if isinstance(item, UUID) else UUID(str(item)) for item in value]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]
