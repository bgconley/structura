# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.storage import ObjectStorage

SVG_MIME = "image/svg+xml"


class PreviewError(Exception):
    pass


def generate_phase1_preview(document_id: UUID, *, storage: ObjectStorage | None = None) -> None:
    object_storage = storage or ObjectStorage()
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  d.id,
                  d.title,
                  d.original_filename,
                  d.document_family::text AS document_family,
                  a.mime_type,
                  a.byte_size,
                  a.sha256
                FROM documents d
                JOIN document_assets a ON a.id = d.canonical_asset_id
                WHERE d.id = %s
                  AND d.deleted_at IS NULL
                """,
                (document_id,),
            )
            row = cur.fetchone()
            if not row:
                raise PreviewError("Document original asset not found.")

            thumbnail = _thumbnail_svg(row)
            preview = _page_preview_svg(row)
            thumbnail_object = object_storage.store_bytes(
                thumbnail,
                kind="derived",
                role=f"thumbnail-{document_id}",
            )
            preview_object = object_storage.store_bytes(
                preview,
                kind="derived",
                role=f"page-preview-{document_id}-1",
            )

            thumbnail_asset_id = _upsert_asset(
                cur,
                document_id=document_id,
                asset_role="thumbnail",
                page_number=1,
                uri=thumbnail_object.uri,
                mime_type=SVG_MIME,
                byte_size=thumbnail_object.byte_size,
                sha256=thumbnail_object.sha256,
                metadata={
                    "previewStatus": "fallback_generated",
                    "previewKind": "phase1_svg_thumbnail",
                },
            )
            page_asset_id = _upsert_asset(
                cur,
                document_id=document_id,
                asset_role="page_image",
                page_number=1,
                uri=preview_object.uri,
                mime_type=SVG_MIME,
                byte_size=preview_object.byte_size,
                sha256=preview_object.sha256,
                metadata={
                    "previewStatus": "fallback_generated",
                    "previewKind": "phase1_svg_page_preview",
                },
            )
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
                    image_asset_id,
                    thumbnail_asset_id,
                    metadata_json
                  )
                VALUES (%s, 1, 612, 792, 0, NULL, %s, %s, %s::jsonb)
                ON CONFLICT (document_id, page_number) DO UPDATE
                SET image_asset_id = EXCLUDED.image_asset_id,
                    thumbnail_asset_id = EXCLUDED.thumbnail_asset_id,
                    metadata_json = document_pages.metadata_json || EXCLUDED.metadata_json,
                    updated_at = now()
                """,
                (
                    document_id,
                    page_asset_id,
                    thumbnail_asset_id,
                    Jsonb(
                        {
                            "previewStatus": "fallback_generated",
                            "phase": "phase1",
                            "source": "original_asset",
                        }
                    ),
                ),
            )
        conn.commit()


def _upsert_asset(
    cur: Any,
    *,
    document_id: UUID,
    asset_role: str,
    page_number: int,
    uri: str,
    mime_type: str,
    byte_size: int,
    sha256: str,
    metadata: Mapping[str, Any],
) -> UUID:
    cur.execute(
        """
        SELECT id
        FROM document_assets
        WHERE document_id = %s
          AND asset_role = %s
          AND page_number = %s
          AND is_current
        """,
        (document_id, asset_role, page_number),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            """
            UPDATE document_assets
            SET uri = %s,
                mime_type = %s,
                byte_size = %s,
                sha256 = %s,
                metadata_json = metadata_json || %s::jsonb,
                updated_at = now()
            WHERE id = %s
            RETURNING id
            """,
            (uri, mime_type, byte_size, sha256, Jsonb(dict(metadata)), existing["id"]),
        )
    else:
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
                metadata_json
              )
            VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                document_id,
                asset_role,
                page_number,
                uri,
                mime_type,
                byte_size,
                sha256,
                Jsonb(dict(metadata)),
            ),
        )
    row = cur.fetchone()
    if not row:
        raise PreviewError("Preview asset upsert failed.")
    return cast(UUID, row["id"])


def _thumbnail_svg(row: Mapping[str, Any]) -> bytes:
    title = _escape_svg(str(row["title"]))
    family = _escape_svg(str(row["document_family"]).replace("_", " ").title())
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="240" height="304" viewBox="0 0 240 304">
  <rect width="240" height="304" rx="20" fill="#ffffff"/>
  <rect x="1" y="1" width="238" height="302" rx="19" fill="none" stroke="#CBD5E1" stroke-width="2"/>
  <rect x="28" y="28" width="184" height="20" rx="3" fill="#E2ECF8"/>
  <rect x="28" y="72" width="176" height="5" rx="2.5" fill="#CBD5E1"/>
  <rect x="28" y="94" width="148" height="5" rx="2.5" fill="#D8E0EA"/>
  <rect x="28" y="116" width="166" height="5" rx="2.5" fill="#D8E0EA"/>
  <rect x="28" y="138" width="132" height="5" rx="2.5" fill="#D8E0EA"/>
  <rect x="28" y="190" width="184" height="56" rx="8" fill="#F7F9FC" stroke="#D8DEE8"/>
  <text x="38" y="214" font-family="Inter, Arial, sans-serif" font-size="15" font-weight="700" fill="#182235">{title[:22]}</text>
  <text x="38" y="237" font-family="Inter, Arial, sans-serif" font-size="12" fill="#64748B">{family}</text>
</svg>""".encode()


def _page_preview_svg(row: Mapping[str, Any]) -> bytes:
    title = _escape_svg(str(row["title"]))
    filename = _escape_svg(str(row.get("original_filename") or "Original document"))
    sha = str(row.get("sha256") or "")[:12]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="1240" viewBox="0 0 960 1240">
  <rect width="960" height="1240" fill="#F7F9FC"/>
  <rect x="110" y="80" width="740" height="1080" rx="8" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="2"/>
  <rect x="180" y="150" width="600" height="34" rx="3" fill="#E2ECF8"/>
  <text x="180" y="245" font-family="Inter, Arial, sans-serif" font-size="30" font-weight="700" fill="#182235">{title[:42]}</text>
  <text x="180" y="288" font-family="Inter, Arial, sans-serif" font-size="18" fill="#64748B">{filename[:64]}</text>
  <text x="180" y="326" font-family="Inter, Arial, sans-serif" font-size="16" fill="#64748B">SHA-256 {sha}</text>
  <rect x="180" y="410" width="600" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="462" width="560" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="514" width="520" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="566" width="480" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="618" width="600" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="670" width="530" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="722" width="560" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="820" width="520" height="68" rx="7" fill="#EAF3FF" stroke="#2563EB" stroke-width="2"/>
  <text x="210" y="862" font-family="Inter, Arial, sans-serif" font-size="18" font-weight="700" fill="#2563EB">Phase 1 preview generated</text>
  <text x="210" y="925" font-family="Inter, Arial, sans-serif" font-size="16" fill="#64748B">Full page rendering and Docling extraction are prepared for Phase 3.</text>
</svg>""".encode()


def _escape_svg(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
