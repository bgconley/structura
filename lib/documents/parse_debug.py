from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lib.db.connection import db_connection


@dataclass(frozen=True)
class ParseDebugLimits:
    page_limit: int = 50
    element_limit: int = 100
    table_limit: int = 50
    chunk_limit: int = 100
    job_limit: int = 25


def get_parse_debug_view(
    *,
    document_id: UUID,
    household_id: UUID,
    limits: ParseDebugLimits | None = None,
) -> dict[str, object] | None:
    active_limits = limits or ParseDebugLimits()
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id,
                  title,
                  page_count,
                  canonical_asset_id,
                  metadata_json
                FROM documents
                WHERE id = %s
                  AND household_id = %s
                  AND deleted_at IS NULL
                """,
                (document_id, household_id),
            )
            document = cur.fetchone()
            if not document:
                return None

            cur.execute(
                """
                SELECT
                  id,
                  asset_role::text AS asset_role,
                  page_number,
                  mime_type,
                  byte_size,
                  sha256,
                  model_name,
                  model_version,
                  metadata_json,
                  created_at,
                  updated_at
                FROM document_assets
                WHERE document_id = %s
                  AND asset_role IN ('docling_json', 'docling_md', 'docling_html')
                  AND is_current
                ORDER BY
                  CASE asset_role
                    WHEN 'docling_json' THEN 0
                    WHEN 'docling_md' THEN 1
                    ELSE 2
                  END,
                  created_at DESC
                """,
                (document_id,),
            )
            assets = [_asset_row(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  page_number,
                  width_points,
                  height_points,
                  rotation_degrees,
                  has_text_layer,
                  text_content,
                  ocr_confidence,
                  image_asset_id,
                  thumbnail_asset_id,
                  metadata_json
                FROM document_pages
                WHERE document_id = %s
                ORDER BY page_number
                LIMIT %s
                """,
                (document_id, active_limits.page_limit),
            )
            pages = [_page_row(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  e.id,
                  p.page_number,
                  e.element_type::text AS element_type,
                  e.ordinal,
                  e.bbox_json,
                  e.text_content,
                  e.confidence,
                  e.source_ref,
                  e.metadata_json
                FROM document_elements e
                JOIN document_pages p ON p.id = e.page_id
                WHERE e.document_id = %s
                ORDER BY p.page_number, e.ordinal, e.created_at
                LIMIT %s
                """,
                (document_id, active_limits.element_limit),
            )
            elements = [_element_row(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  t.id,
                  p.page_number,
                  t.table_index,
                  t.row_count,
                  t.column_count,
                  t.confidence,
                  t.metadata_json
                FROM document_tables t
                JOIN document_pages p ON p.id = t.page_id
                WHERE t.document_id = %s
                ORDER BY p.page_number, t.table_index
                LIMIT %s
                """,
                (document_id, active_limits.table_limit),
            )
            tables = [_table_row(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  id,
                  chunk_index,
                  chunk_kind,
                  page_start,
                  page_end,
                  heading_path,
                  text_content,
                  token_count,
                  char_count,
                  metadata_json
                FROM document_chunks
                WHERE document_id = %s
                ORDER BY chunk_index
                LIMIT %s
                """,
                (document_id, active_limits.chunk_limit),
            )
            chunks = [_chunk_row(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                  id,
                  job_type::text AS job_type,
                  status::text AS status,
                  created_at,
                  started_at,
                  finished_at,
                  attempt_count,
                  max_attempts,
                  queue_name,
                  worker_name,
                  error_json,
                  result_json
                FROM pipeline_jobs
                WHERE document_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (document_id, active_limits.job_limit),
            )
            jobs = [_job_row(row) for row in cur.fetchall()]

    return {
        "document": {
            "id": str(document["id"]),
            "title": document["title"],
            "pageCount": document["page_count"],
            "canonicalAssetId": (
                str(document["canonical_asset_id"]) if document["canonical_asset_id"] else None
            ),
            "metadata": document["metadata_json"] or {},
        },
        "artifacts": assets,
        "pages": pages,
        "elements": elements,
        "tables": tables,
        "chunks": chunks,
        "jobs": jobs,
        "limits": active_limits.__dict__,
    }


def _asset_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "assetRole": row["asset_role"],
        "pageNumber": row["page_number"],
        "mimeType": row["mime_type"],
        "byteSize": row["byte_size"],
        "sha256": row["sha256"],
        "modelName": row["model_name"],
        "modelVersion": row["model_version"],
        "assetUrl": f"/api/v1/assets/{row['id']}",
        "metadata": row["metadata_json"] or {},
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _page_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "pageNumber": row["page_number"],
        "width": row["width_points"],
        "height": row["height_points"],
        "rotationDegrees": row["rotation_degrees"],
        "hasTextLayer": row["has_text_layer"],
        "textPreview": _truncate(row["text_content"], 600),
        "ocrConfidence": row["ocr_confidence"],
        "imageUrl": f"/api/v1/assets/{row['image_asset_id']}" if row["image_asset_id"] else None,
        "thumbnailUrl": (
            f"/api/v1/assets/{row['thumbnail_asset_id']}" if row["thumbnail_asset_id"] else None
        ),
        "metadata": row["metadata_json"] or {},
    }


def _element_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "pageNumber": row["page_number"],
        "elementType": row["element_type"],
        "ordinal": row["ordinal"],
        "bbox": row["bbox_json"],
        "textPreview": _truncate(row["text_content"], 400),
        "confidence": row["confidence"],
        "sourceRef": row["source_ref"],
        "metadata": row["metadata_json"] or {},
    }


def _table_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "pageNumber": row["page_number"],
        "tableIndex": row["table_index"],
        "rowCount": row["row_count"],
        "columnCount": row["column_count"],
        "confidence": row["confidence"],
        "metadata": row["metadata_json"] or {},
    }


def _chunk_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "chunkIndex": row["chunk_index"],
        "chunkKind": row["chunk_kind"],
        "pageStart": row["page_start"],
        "pageEnd": row["page_end"],
        "headingPath": row["heading_path"],
        "textPreview": _truncate(row["text_content"], 600),
        "tokenCount": row["token_count"],
        "charCount": row["char_count"],
        "metadata": row["metadata_json"] or {},
    }


def _job_row(row: dict[str, object]) -> dict[str, object]:
    return {
        "jobId": str(row["id"]),
        "jobType": row["job_type"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "startedAt": row["started_at"],
        "finishedAt": row["finished_at"],
        "attemptCount": row["attempt_count"],
        "maxAttempts": row["max_attempts"],
        "queueName": row["queue_name"],
        "workerName": row["worker_name"],
        "error": row["error_json"] or {},
        "result": row["result_json"] or {},
    }


def _truncate(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    return value if len(value) <= limit else f"{value[:limit]}..."
