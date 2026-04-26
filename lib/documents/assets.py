from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb


class DocumentAssetError(Exception):
    pass


def upsert_current_asset(
    cur: Any,
    *,
    document_id: UUID,
    asset_role: str,
    uri: str,
    mime_type: str,
    byte_size: int,
    sha256: str,
    page_number: int | None = None,
    metadata: Mapping[str, Any] | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
) -> UUID:
    """Insert a new current asset version without mutating historical content pointers."""

    cur.execute(
        """
        SELECT id, version_no, sha256
        FROM document_assets
        WHERE document_id = %s
          AND asset_role = %s
          AND COALESCE(page_number, 0) = COALESCE(%s::integer, 0)
          AND is_current
        ORDER BY version_no DESC, created_at DESC
        LIMIT 1
        FOR UPDATE
        """,
        (document_id, asset_role, page_number),
    )
    current = cur.fetchone()
    metadata_json = Jsonb(dict(metadata or {}))

    if current and current["sha256"] == sha256:
        cur.execute(
            """
            UPDATE document_assets
            SET uri = %s,
                mime_type = %s,
                byte_size = %s,
                metadata_json = metadata_json || %s::jsonb,
                model_name = COALESCE(%s, model_name),
                model_version = COALESCE(%s, model_version),
                updated_at = now()
            WHERE id = %s
            RETURNING id
            """,
            (
                uri,
                mime_type,
                byte_size,
                metadata_json,
                model_name,
                model_version,
                current["id"],
            ),
        )
        row = cur.fetchone()
        if not row:
            raise DocumentAssetError("Current asset update failed.")
        return cast(UUID, row["id"])

    cur.execute(
        """
        SELECT COALESCE(max(version_no), 0) + 1 AS next_version
        FROM document_assets
        WHERE document_id = %s
          AND asset_role = %s
          AND COALESCE(page_number, 0) = COALESCE(%s::integer, 0)
        """,
        (document_id, asset_role, page_number),
    )
    version_row = cur.fetchone()
    next_version = int(version_row["next_version"] if version_row else 1)

    if current:
        cur.execute(
            """
            UPDATE document_assets
            SET is_current = false,
                updated_at = now()
            WHERE id = %s
            """,
            (current["id"],),
        )

    cur.execute(
        """
        INSERT INTO document_assets
          (
            document_id,
            asset_role,
            version_no,
            page_number,
            uri,
            mime_type,
            byte_size,
            sha256,
            model_name,
            model_version,
            metadata_json,
            is_current
          )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, true)
        RETURNING id
        """,
        (
            document_id,
            asset_role,
            next_version,
            page_number,
            uri,
            mime_type,
            byte_size,
            sha256,
            model_name,
            model_version,
            metadata_json,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise DocumentAssetError("Current asset insert failed.")
    return cast(UUID, row["id"])
