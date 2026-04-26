from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.documents.parse_models import CanonicalParseResult


def replace_relational_parse(cur: Any, document_id: UUID, result: CanonicalParseResult) -> None:
    cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM document_tables WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM document_elements WHERE document_id = %s", (document_id,))
    cur.execute("DELETE FROM document_pages WHERE document_id = %s", (document_id,))

    cur.execute(
        """
        SELECT
          household_id,
          document_family::text AS document_family,
          document_subtype,
          document_date,
          sensitivity::text AS sensitivity,
          counterparty_display,
          primary_folder_id
        FROM documents
        WHERE id = %s
        """,
        (document_id,),
    )
    document = cur.fetchone()
    if not document:
        raise ValueError("Document not found.")

    page_ids: dict[int, UUID] = {}
    for page in result.pages:
        cur.execute(
            """
            INSERT INTO document_pages
              (
                document_id,
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
              )
            VALUES (
              %s,
              %s,
              %s,
              %s,
              %s,
              %s,
              %s,
              %s,
              (
                SELECT id
                FROM document_assets
                WHERE document_id = %s
                  AND asset_role = 'page_image'
                  AND page_number = %s
                  AND is_current
                ORDER BY created_at DESC
                LIMIT 1
              ),
              (
                SELECT id
                FROM document_assets
                WHERE document_id = %s
                  AND asset_role = 'thumbnail'
                  AND page_number = %s
                  AND is_current
                ORDER BY created_at DESC
                LIMIT 1
              ),
              %s::jsonb
            )
            RETURNING id
            """,
            (
                document_id,
                page.page_number,
                page.width,
                page.height,
                page.rotation_degrees,
                page.has_text_layer,
                page.text,
                page.ocr_confidence,
                document_id,
                page.page_number,
                document_id,
                page.page_number,
                Jsonb({"phase": "phase3", **dict(page.metadata)}),
            ),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Document page insert failed.")
        page_ids[page.page_number] = row["id"]

    _insert_elements(cur, document_id, result, page_ids)
    _insert_tables(cur, document_id, result, page_ids)
    _insert_chunks(cur, document_id, result, document)


def update_document_parse_state(
    cur: Any,
    *,
    document_id: UUID,
    docling_asset_id: UUID,
    result: CanonicalParseResult,
    job_id: UUID | None,
) -> None:
    page_count = len(result.pages)
    is_digital_native = any(page.has_text_layer for page in result.pages)
    has_handwriting = any(
        bool(page.metadata.get("hasHandwriting") or page.metadata.get("has_handwriting"))
        for page in result.pages
    )
    cur.execute(
        """
        UPDATE documents
        SET canonical_asset_id = %s,
            page_count = %s,
            is_digital_native = %s,
            has_handwriting = %s,
            metadata_json = metadata_json || %s::jsonb,
            updated_at = now()
        WHERE id = %s
        """,
        (
            docling_asset_id,
            page_count,
            is_digital_native,
            has_handwriting,
            Jsonb(
                {
                    "phase": "phase3",
                    "phase3": {
                        "parseStatus": "succeeded",
                        "pageCount": page_count,
                        "elementCount": len(result.elements),
                        "tableCount": len(result.tables),
                        "chunkCount": len(result.chunks),
                        "currentDoclingAssetId": str(docling_asset_id),
                        "lastDoclingJobId": str(job_id) if job_id else None,
                        "converter": {
                            "name": result.converter_name,
                            "version": result.converter_version,
                        },
                        "warnings": result.warnings,
                    },
                }
            ),
            document_id,
        ),
    )


def _insert_elements(
    cur: Any,
    document_id: UUID,
    result: CanonicalParseResult,
    page_ids: dict[int, UUID],
) -> None:
    for element in result.elements:
        page_id = page_ids.get(element.page_number)
        if not page_id:
            continue
        cur.execute(
            """
            INSERT INTO document_elements
              (
                document_id,
                page_id,
                element_type,
                ordinal,
                bbox_json,
                text_content,
                confidence,
                source_engine,
                source_ref,
                metadata_json
              )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, 'docling', %s, %s::jsonb)
            """,
            (
                document_id,
                page_id,
                _safe_element_type(element.element_type),
                max(element.ordinal, 1),
                Jsonb(element.bbox) if element.bbox is not None else None,
                element.text,
                element.confidence,
                element.source_ref,
                Jsonb({"phase": "phase3", **dict(element.metadata)}),
            ),
        )


def _insert_tables(
    cur: Any,
    document_id: UUID,
    result: CanonicalParseResult,
    page_ids: dict[int, UUID],
) -> None:
    for table in result.tables:
        page_id = page_ids.get(table.page_number)
        if not page_id:
            continue
        cur.execute(
            """
            INSERT INTO document_tables
              (
                document_id,
                page_id,
                table_index,
                row_count,
                column_count,
                table_json,
                table_html,
                table_markdown,
                confidence,
                source_engine,
                metadata_json
              )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, 'docling', %s::jsonb)
            """,
            (
                document_id,
                page_id,
                max(table.table_index, 1),
                table.row_count,
                table.column_count,
                Jsonb(dict(table.table_json)),
                table.table_html,
                table.table_markdown,
                table.confidence,
                Jsonb({"phase": "phase3", **dict(table.metadata)}),
            ),
        )


def _insert_chunks(
    cur: Any,
    document_id: UUID,
    result: CanonicalParseResult,
    document: dict[str, Any],
) -> None:
    for chunk in result.chunks:
        cur.execute(
            """
            INSERT INTO document_chunks
              (
                document_id,
                chunk_index,
                chunk_kind,
                page_start,
                page_end,
                heading_path,
                text_content,
                markdown_content,
                token_count,
                char_count,
                metadata_json,
                household_id,
                document_family_snapshot,
                document_subtype_snapshot,
                document_date_snapshot,
                sensitivity_snapshot,
                counterparty_snapshot,
                primary_folder_id,
                bm25_text
              )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
              %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                document_id,
                max(chunk.chunk_index, 1),
                chunk.chunk_kind,
                chunk.page_start,
                chunk.page_end,
                chunk.heading_path,
                chunk.text,
                chunk.markdown,
                chunk.token_count,
                len(chunk.text),
                Jsonb({"phase": "phase3", **dict(chunk.metadata)}),
                document["household_id"],
                document["document_family"],
                document["document_subtype"],
                document["document_date"],
                document["sensitivity"],
                document["counterparty_display"],
                document["primary_folder_id"],
                chunk.text,
            ),
        )


def _safe_element_type(value: str) -> str:
    allowed = {
        "paragraph",
        "heading",
        "table",
        "figure",
        "form_field",
        "checkbox",
        "signature",
        "header",
        "footer",
        "caption",
        "list_item",
        "key_value_pair",
        "code_block",
        "other",
    }
    return value if value in allowed else "other"
