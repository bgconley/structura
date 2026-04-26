from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lib.contracts import DocumentAsset, DocumentDetail, DocumentPage, DocumentSummary
from lib.db.connection import db_connection
from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
)

DOCUMENT_LIST_COUNT_SQL = """
SELECT count(*) AS total
FROM documents d
LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
WHERE d.deleted_at IS NULL
  AND document_is_readable(d.id, %s, %s, %s)
  AND (
    %s::text IS NULL
    OR d.title ILIKE %s
    OR d.original_filename ILIKE %s
    OR d.counterparty_display ILIKE %s
  )
  AND (%s::text IS NULL OR d.document_family::text = %s)
  AND (%s::text IS NULL OR d.review_status::text = %s)
  AND (
    %s::uuid IS NULL
    OR EXISTS (
      SELECT 1 FROM document_folder_memberships dfm
      WHERE dfm.document_id = d.id
        AND dfm.folder_id = %s
    )
  )
"""

DOCUMENT_LIST_SELECT_SQL = """
SELECT
  d.id,
  d.title,
  d.document_family::text AS family,
  d.lifecycle_state::text AS lifecycle_state,
  d.review_status::text AS review_status,
  d.created_at,
  d.document_date,
  d.counterparty_display,
  a.total_amount AS amount_total,
  (
    SELECT ta.id
    FROM document_assets ta
    WHERE ta.document_id = d.id
      AND ta.asset_role = 'thumbnail'
      AND ta.is_current
    ORDER BY ta.page_number NULLS LAST, ta.created_at DESC
    LIMIT 1
  ) AS thumbnail_asset_id,
  COALESCE(
    (
      SELECT array_agg(
        COALESCE(f.path_cache, '/' || f.name)
        ORDER BY dfm.is_primary DESC, COALESCE(f.path_cache, '/' || f.name), f.name
      )
      FROM document_folder_memberships dfm
      JOIN folders f ON f.id = dfm.folder_id
      WHERE dfm.document_id = d.id
    ),
    ARRAY[]::text[]
  ) AS folder_paths,
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
LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
WHERE d.deleted_at IS NULL
  AND document_is_readable(d.id, %s, %s, %s)
  AND (
    %s::text IS NULL
    OR d.title ILIKE %s
    OR d.original_filename ILIKE %s
    OR d.counterparty_display ILIKE %s
  )
  AND (%s::text IS NULL OR d.document_family::text = %s)
  AND (%s::text IS NULL OR d.review_status::text = %s)
  AND (
    %s::uuid IS NULL
    OR EXISTS (
      SELECT 1 FROM document_folder_memberships dfm
      WHERE dfm.document_id = d.id
        AND dfm.folder_id = %s
    )
  )
ORDER BY d.created_at DESC, d.id DESC
LIMIT %s OFFSET %s
"""


@dataclass(frozen=True)
class DocumentListFilters:
    access: DocumentAccessContext
    query_text: str | None = None
    family: str | None = None
    review_status: str | None = None
    folder_id: UUID | None = None
    limit: int = 50
    offset: int = 0


def list_document_summaries(filters: DocumentListFilters) -> tuple[list[DocumentSummary], int]:
    query_like = f"%{filters.query_text}%" if filters.query_text else None
    filter_params: list[object] = [
        *document_read_access_params(filters.access),
        filters.query_text,
        query_like,
        query_like,
        query_like,
        filters.family,
        filters.family,
        filters.review_status,
        filters.review_status,
        filters.folder_id,
        filters.folder_id,
    ]

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(DOCUMENT_LIST_COUNT_SQL, filter_params)
            total_row = cur.fetchone()
            cur.execute(DOCUMENT_LIST_SELECT_SQL, [*filter_params, filters.limit, filters.offset])
            rows = cur.fetchall()

    total = int(total_row["total"] if total_row else 0)
    return [_document_summary_from_row(row) for row in rows], total


def get_document_detail(document_id: UUID, access: DocumentAccessContext) -> DocumentDetail | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  d.id,
                  d.title,
                  d.description,
                  d.document_family::text AS family,
                  d.lifecycle_state::text AS lifecycle_state,
                  d.review_status::text AS review_status,
                  d.created_at,
                  d.document_date,
                  d.filing_notes,
                  d.primary_folder_id,
                  d.counterparty_display,
                  a.total_amount AS amount_total,
                  (
                    SELECT ta.id
                    FROM document_assets ta
                    WHERE ta.document_id = d.id
                      AND ta.asset_role = 'thumbnail'
                      AND ta.is_current
                    ORDER BY ta.page_number NULLS LAST, ta.created_at DESC
                    LIMIT 1
                  ) AS thumbnail_asset_id,
                  COALESCE(
                    (
                      SELECT array_agg(
                        COALESCE(f.path_cache, '/' || f.name)
                        ORDER BY dfm.is_primary DESC, COALESCE(f.path_cache, '/' || f.name), f.name
                      )
                      FROM document_folder_memberships dfm
                      JOIN folders f ON f.id = dfm.folder_id
                      WHERE dfm.document_id = d.id
                    ),
                    ARRAY[]::text[]
                  ) AS folder_paths,
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
                      SELECT array_agg(t.name::text ORDER BY t.name::text)
                      FROM document_tags dt
                      JOIN tags t ON t.id = dt.tag_id
                      WHERE dt.document_id = d.id
                    ),
                    ARRAY[]::text[]
                  ) AS tags
                FROM documents d
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE d.id = %s
                  AND d.deleted_at IS NULL
                  AND document_is_readable(d.id, %s, %s, %s)
                """,
                (document_id, *document_read_access_params(access)),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute(
                """
                SELECT id, asset_role::text AS asset_role, page_number, mime_type, sha256
                FROM document_assets
                WHERE document_id = %s
                  AND is_current
                ORDER BY
                  CASE asset_role
                    WHEN 'original' THEN 0
                    WHEN 'thumbnail' THEN 1
                    WHEN 'page_image' THEN 2
                    ELSE 3
                  END,
                  page_number NULLS LAST,
                  created_at DESC
                """,
                (document_id,),
            )
            asset_rows = cur.fetchall()
            cur.execute(
                """
                SELECT
                  p.page_number,
                  p.width_points,
                  p.height_points,
                  p.rotation_degrees,
                  p.text_content,
                  p.image_asset_id
                FROM document_pages p
                WHERE p.document_id = %s
                ORDER BY p.page_number
                """,
                (document_id,),
            )
            page_rows = cur.fetchall()

    summary = _document_summary_from_row(row)
    pages = [
        DocumentPage.model_validate(
            {
                "pageNumber": page["page_number"],
                "width": page["width_points"],
                "height": page["height_points"],
                "rotationDegrees": page["rotation_degrees"],
                "textContent": page["text_content"],
                "imageUrl": (
                    f"/api/v1/assets/{page['image_asset_id']}" if page["image_asset_id"] else None
                ),
            }
        )
        for page in page_rows
    ]
    assets = [
        DocumentAsset.model_validate(
            {
                "id": asset["id"],
                "assetRole": asset["asset_role"],
                "pageNumber": asset["page_number"],
                "mimeType": asset["mime_type"] or "application/octet-stream",
                "assetUrl": f"/api/v1/assets/{asset['id']}",
                "sha256": asset["sha256"],
            }
        )
        for asset in asset_rows
    ]
    return DocumentDetail.model_validate(
        {
            **summary.model_dump(by_alias=True),
            "description": row.get("description"),
            "pages": [page.model_dump(by_alias=True) for page in pages],
            "assets": [asset.model_dump(by_alias=True) for asset in assets],
            "extractions": [],
            "relationships": [],
            "fields": [],
            "lineItems": [],
            "tags": _string_list(row.get("tags")),
            "folderIds": _uuid_list(row.get("folder_ids")),
            "primaryFolderId": row.get("primary_folder_id"),
            "filingNotes": row.get("filing_notes"),
        }
    )


def _document_summary_from_row(row: dict[str, object]) -> DocumentSummary:
    thumbnail_asset_id = row.get("thumbnail_asset_id")
    return DocumentSummary.model_validate(
        {
            "id": row["id"],
            "title": row["title"],
            "family": row["family"],
            "lifecycleState": row["lifecycle_state"],
            "reviewStatus": row["review_status"],
            "createdAt": row["created_at"],
            "documentDate": row.get("document_date"),
            "amountTotal": row.get("amount_total"),
            "counterpartyDisplay": row.get("counterparty_display"),
            "thumbnailUrl": f"/api/v1/assets/{thumbnail_asset_id}" if thumbnail_asset_id else None,
            "folderPaths": _string_list(row.get("folder_paths")),
            "tags": _string_list(row.get("tags")),
        }
    )


def _uuid_list(value: object) -> list[UUID]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item if isinstance(item, UUID) else UUID(str(item)) for item in value]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]
