from __future__ import annotations

from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext, document_read_access_params
from lib.extraction.errors import ExtractionRepositoryError
from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)


def load_extraction_source(document_id: UUID) -> ExtractionSourceDocument:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  d.id,
                  d.household_id,
                  d.title,
                  d.original_filename,
                  d.document_family::text AS family,
                  d.document_subtype,
                  d.sensitivity::text AS sensitivity,
                  d.document_date,
                  d.counterparty_display,
                  d.primary_folder_id,
                  d.metadata_json,
                  a.mime_type
                FROM documents d
                LEFT JOIN document_assets a ON a.document_id = d.id
                 AND a.asset_role = 'original'
                 AND a.is_current
                WHERE d.id = %s
                  AND d.deleted_at IS NULL
                """,
                (document_id,),
            )
            document = cur.fetchone()
            if not document:
                raise ExtractionRepositoryError("Document not found.")
            if not document["household_id"]:
                raise ExtractionRepositoryError("Document is missing household ownership.")
            pages = _page_rows(cur, document_id)
            elements = _element_rows(cur, document_id)
            tables = _table_rows(cur, document_id)

    return ExtractionSourceDocument(
        document_id=document["id"],
        household_id=document["household_id"],
        title=document["title"],
        original_filename=document["original_filename"],
        mime_type=document["mime_type"],
        family=document["family"],
        subtype=document["document_subtype"],
        sensitivity=document["sensitivity"],
        document_date=document["document_date"],
        counterparty_display=document["counterparty_display"],
        primary_folder_id=document["primary_folder_id"],
        metadata=dict(document["metadata_json"] or {}),
        pages=[
            ParsedPageText(
                page_id=cast(UUID, row["id"]),
                page_number=_row_int(row["page_number"], "page_number"),
                text=str(row["text_content"] or ""),
                image_asset_uri=str(row["image_uri"]) if row.get("image_uri") else None,
                image_mime_type=(
                    str(row["image_mime_type"]) if row.get("image_mime_type") else None
                ),
                image_sha256=str(row["image_sha256"]) if row.get("image_sha256") else None,
                width_points=_row_float(row.get("width_points")),
                height_points=_row_float(row.get("height_points")),
                rotation_degrees=_row_int(row["rotation_degrees"], "rotation_degrees"),
                has_text_layer=(
                    bool(row["has_text_layer"]) if row.get("has_text_layer") is not None else None
                ),
                ocr_confidence=_row_float(row.get("ocr_confidence")),
                metadata=(
                    dict(row["metadata_json"]) if isinstance(row["metadata_json"], dict) else {}
                ),
            )
            for row in pages
        ],
        elements=[
            ParsedElementText(
                element_id=cast(UUID, row["id"]),
                page_number=_row_int(row["page_number"], "page_number"),
                ordinal=_row_int(row["ordinal"], "ordinal"),
                text=str(row["text_content"] or ""),
                bbox=row["bbox_json"],
                metadata=(
                    dict(row["metadata_json"]) if isinstance(row["metadata_json"], dict) else {}
                ),
            )
            for row in elements
        ],
        tables=[
            ParsedTableText(
                table_id=cast(UUID, row["id"]),
                page_number=_row_int(row["page_number"], "page_number"),
                table_index=_row_int(row["table_index"], "table_index"),
                table_markdown=(
                    str(row["table_markdown"]) if row["table_markdown"] is not None else None
                ),
                table_json=(dict(row["table_json"]) if isinstance(row["table_json"], dict) else {}),
                element_id=cast(UUID, row["element_id"]) if row.get("element_id") else None,
                bbox=row["bbox_json"],
                metadata=(
                    dict(row["metadata_json"]) if isinstance(row["metadata_json"], dict) else {}
                ),
            )
            for row in tables
        ],
    )


def require_document_readable(document_id: UUID, access: DocumentAccessContext) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_is_readable(id, %s, %s, %s) AS readable
                FROM documents
                WHERE id = %s
                  AND deleted_at IS NULL
                """,
                (*document_read_access_params(access), document_id),
            )
            row = cur.fetchone()
    if not row or not row["readable"]:
        raise ExtractionRepositoryError("Document not found.")


def _row_int(value: object, column: str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ExtractionRepositoryError(f"Unexpected non-integer value for {column}.")


def _row_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return None


def _page_rows(cur: Any, document_id: UUID) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT
          p.id,
          p.page_number,
          p.text_content,
          p.width_points,
          p.height_points,
          p.rotation_degrees,
          p.has_text_layer,
          p.ocr_confidence,
          p.metadata_json,
          a.uri AS image_uri,
          a.mime_type AS image_mime_type,
          a.sha256 AS image_sha256
        FROM document_pages p
        LEFT JOIN document_assets a ON a.id = p.image_asset_id
        WHERE p.document_id = %s
        ORDER BY p.page_number
        """,
        (document_id,),
    )
    return list(cur.fetchall())


def _element_rows(cur: Any, document_id: UUID) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT
          e.id,
          p.page_number,
          e.ordinal,
          e.text_content,
          e.bbox_json,
          e.metadata_json
        FROM document_elements e
        JOIN document_pages p ON p.id = e.page_id
        WHERE e.document_id = %s
        ORDER BY p.page_number, e.ordinal
        """,
        (document_id,),
    )
    return list(cur.fetchall())


def _table_rows(cur: Any, document_id: UUID) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT
          t.id,
          p.page_number,
          t.table_index,
          t.table_markdown,
          t.table_json,
          t.element_id,
          COALESCE(te.bbox_json, t.metadata_json -> 'bbox') AS bbox_json,
          t.metadata_json
        FROM document_tables t
        JOIN document_pages p ON p.id = t.page_id
        LEFT JOIN document_elements te ON te.id = t.element_id
        WHERE t.document_id = %s
        ORDER BY p.page_number, t.table_index
        """,
        (document_id,),
    )
    return list(cur.fetchall())
