from __future__ import annotations

from uuid import UUID

from lib.contracts import DocumentAsset, DocumentDetail, DocumentPage
from lib.db.connection import db_connection
from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
)
from lib.documents.summary_mapping import document_summary_from_row, string_list, uuid_list
from lib.extraction.candidate_repository import value_from_candidate_row
from lib.relationships.service import RelationshipService


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
                  ) AS tags,
                  (
                    SELECT count(*)::int
                    FROM document_relationships dr
                    WHERE dr.status IN ('suggested', 'confirmed')
                      AND d.id IN (dr.from_document_id, dr.to_document_id)
                  ) AS related_count
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
            cur.execute(
                """
                SELECT *
                FROM canonical_fields
                WHERE document_id = %s
                ORDER BY field_path, ordinal
                """,
                (document_id,),
            )
            field_rows = cur.fetchall()
            cur.execute(
                """
                SELECT *
                FROM canonical_line_items
                WHERE document_id = %s
                ORDER BY line_item_type, ordinal
                """,
                (document_id,),
            )
            line_item_rows = cur.fetchall()
            cur.execute(
                """
                SELECT
                  id,
                  schema_name,
                  schema_version,
                  status::text AS status,
                  source_engine::text AS source_engine,
                  model_name,
                  model_version,
                  confidence,
                  review_status::text AS review_status,
                  created_at
                FROM document_extractions
                WHERE document_id = %s
                  AND is_current
                ORDER BY created_at DESC
                """,
                (document_id,),
            )
            extraction_rows = cur.fetchall()

    summary = document_summary_from_row(row)
    relationships = RelationshipService().list_relationships(
        access=access,
        document_id=document_id,
        limit=200,
    )
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
            "extractions": [_extraction_payload(row) for row in extraction_rows],
            "relationships": [
                relationship.model_dump(by_alias=True) for relationship in relationships
            ],
            "fields": [_canonical_field_payload(row) for row in field_rows],
            "lineItems": [_canonical_line_item_payload(row) for row in line_item_rows],
            "tags": string_list(row.get("tags")),
            "folderIds": uuid_list(row.get("folder_ids")),
            "primaryFolderId": row.get("primary_folder_id"),
            "filingNotes": row.get("filing_notes"),
        }
    )


def _extraction_payload(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": row["id"],
        "schemaName": row["schema_name"],
        "schemaVersion": row["schema_version"],
        "status": row["status"],
        "sourceEngine": row["source_engine"],
        "modelName": row.get("model_name"),
        "modelVersion": row.get("model_version"),
        "confidence": row.get("confidence"),
        "reviewStatus": row.get("review_status"),
        "createdAt": row.get("created_at"),
    }


def _canonical_field_payload(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": row["id"],
        "fieldPath": row["field_path"],
        "ordinal": row["ordinal"],
        "valueType": row["value_type"],
        "value": value_from_candidate_row(row),
        "currency": row.get("currency_code"),
        "sourceKind": row.get("source_kind"),
        "reviewStatus": row.get("review_status"),
        "evidence": row.get("evidence_json") or [],
        "validation": row.get("validation_json") or {},
        "acceptedAt": row.get("accepted_at"),
    }


def _canonical_line_item_payload(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": row["id"],
        "lineItemType": row["line_item_type"],
        "ordinal": row["ordinal"],
        "description": row.get("description"),
        "netAmount": row.get("net_amount"),
        "currency": row.get("currency_code"),
        "sourceKind": row.get("source_kind"),
        "reviewStatus": row.get("review_status"),
        "evidence": row.get("evidence_json") or [],
    }
