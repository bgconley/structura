from __future__ import annotations

from uuid import UUID

from psycopg import sql

from lib.contracts import DocumentAsset, DocumentDetail, DocumentPage
from lib.db.connection import db_connection
from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
)
from lib.documents.relationship_counts import (
    READABLE_RELATED_COUNT_SQL,
    readable_related_count_params,
)
from lib.documents.summary_mapping import document_summary_from_row, string_list, uuid_list
from lib.extraction.candidate_repository import value_from_candidate_row
from lib.relationships.service import RelationshipService


def get_document_detail(document_id: UUID, access: DocumentAccessContext) -> DocumentDetail | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _document_detail_sql(),
                (
                    *readable_related_count_params(access),
                    document_id,
                    *document_read_access_params(access),
                ),
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
                  p.image_asset_id,
                  p.metadata_json
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
                  extraction_scope,
                  created_at
                FROM document_extractions
                WHERE document_id = %s
                  AND is_current
                  AND extraction_scope IN ('document', 'aggregate')
                ORDER BY created_at DESC
                """,
                (document_id,),
            )
            extraction_rows = cur.fetchall()
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
                  extraction_scope,
                  semantic_annotation_id,
                  source_semantic_region_id,
                  semantic_type,
                  granite_task,
                  model_output_schema_name,
                  model_output_schema_version,
                  normalized_json,
                  normalization_json,
                  metadata_json,
                  created_at
                FROM document_extractions
                WHERE document_id = %s
                  AND is_current
                  AND extraction_scope = 'semantic_region'
                ORDER BY created_at DESC
                """,
                (document_id,),
            )
            semantic_region_extraction_rows = cur.fetchall()
            cur.execute(
                """
                SELECT
                  id,
                  extraction_id,
                  semantic_annotation_id,
                  source_semantic_region_id,
                  semantic_type,
                  source_engine::text AS source_engine,
                  model_output_schema_name,
                  observation_family,
                  field_name,
                  value_type,
                  value_json,
                  confidence,
                  evidence_json,
                  validation_json,
                  status,
                  metadata_json,
                  created_at
                FROM extraction_observations
                WHERE document_id = %s
                ORDER BY created_at DESC
                """,
                (document_id,),
            )
            observation_rows = cur.fetchall()

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
                "qualitySignals": _page_quality_signals(page.get("metadata_json")),
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
            "semanticRegionExtractions": [
                _semantic_region_extraction_payload(row) for row in semantic_region_extraction_rows
            ],
            "observations": [_observation_payload(row) for row in observation_rows],
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


def _document_detail_sql() -> sql.Composed:
    return sql.SQL(
        """
        SELECT
          d.id,
          d.title,
          d.description,
          d.document_family::text AS family,
          d.lifecycle_state::text AS lifecycle_state,
          d.review_status::text AS review_status,
          d.created_at,
          d.metadata_json,
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
          {readable_related_count_sql}
        FROM documents d
        LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
        WHERE d.id = %s
          AND d.deleted_at IS NULL
          AND document_is_readable(d.id, %s, %s, %s)
        """
    ).format(readable_related_count_sql=sql.SQL(READABLE_RELATED_COUNT_SQL))


def _page_quality_signals(metadata: object) -> dict[str, object] | None:
    if not isinstance(metadata, dict):
        return None
    phase8 = metadata.get("phase8")
    if not isinstance(phase8, dict):
        return None
    quality = phase8.get("quality")
    return quality if isinstance(quality, dict) else None


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
        "extractionScope": row.get("extraction_scope"),
        "createdAt": row.get("created_at"),
    }


def _semantic_region_extraction_payload(row: dict[str, object]) -> dict[str, object]:
    payload = _extraction_payload(row)
    payload.update(
        {
            "semanticAnnotationId": row.get("semantic_annotation_id"),
            "sourceSemanticRegionId": row.get("source_semantic_region_id"),
            "semanticType": row.get("semantic_type"),
            "graniteTask": row.get("granite_task"),
            "modelOutputSchemaName": row.get("model_output_schema_name"),
            "modelOutputSchemaVersion": row.get("model_output_schema_version"),
            "normalized": row.get("normalized_json") or {},
            "normalization": row.get("normalization_json") or {},
            "metadata": row.get("metadata_json") or {},
        }
    )
    return payload


def _observation_payload(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": row["id"],
        "extractionId": row.get("extraction_id"),
        "semanticAnnotationId": row.get("semantic_annotation_id"),
        "sourceSemanticRegionId": row.get("source_semantic_region_id"),
        "semanticType": row.get("semantic_type"),
        "sourceEngine": row.get("source_engine"),
        "modelOutputSchemaName": row.get("model_output_schema_name"),
        "observationFamily": row.get("observation_family"),
        "fieldName": row.get("field_name"),
        "valueType": row.get("value_type"),
        "value": row.get("value_json"),
        "confidence": row.get("confidence"),
        "evidence": row.get("evidence_json") or [],
        "validation": row.get("validation_json") or {},
        "status": row.get("status"),
        "metadata": row.get("metadata_json") or {},
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
