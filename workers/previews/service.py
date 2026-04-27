# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.documents.assets import upsert_current_asset
from lib.storage import ObjectStorage, StoredObject, cleanup_unreferenced_stored_object

SVG_MIME = "image/svg+xml"
PREVIEW_RENDERER_NAME = "structura-svg-page-preview"
PREVIEW_RENDERER_VERSION = "phase3.1"


class PreviewError(Exception):
    pass


def generate_phase1_preview(document_id: UUID, *, storage: ObjectStorage | None = None) -> None:
    generate_page_previews(document_id, storage=storage)


def generate_page_previews(
    document_id: UUID,
    *,
    job_id: UUID | None = None,
    storage: ObjectStorage | None = None,
) -> None:
    object_storage = storage or ObjectStorage()
    created_objects: list[StoredObject] = []
    db_committed = False
    with db_connection() as conn:
        try:
            with conn.cursor() as cur:
                document = _document_for_preview(cur, document_id)
                pages = _pages_for_preview(cur, document)
                for page in pages:
                    _generate_page_assets(
                        cur,
                        object_storage,
                        document=document,
                        page=page,
                        job_id=job_id,
                        created_objects=created_objects,
                    )
            conn.commit()
            db_committed = True
        finally:
            if not db_committed:
                _cleanup_created_objects(created_objects)


def _document_for_preview(cur: Any, document_id: UUID) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
          d.id,
          d.title,
          d.original_filename,
          d.document_family::text AS document_family,
          COALESCE(d.page_count, 1) AS page_count,
          a.id AS original_asset_id,
          a.mime_type,
          a.byte_size,
          a.sha256
        FROM documents d
        JOIN document_assets a ON a.document_id = d.id
         AND a.asset_role = 'original'
         AND a.is_current
        WHERE d.id = %s
          AND d.deleted_at IS NULL
        """,
        (document_id,),
    )
    row = cur.fetchone()
    if not row:
        raise PreviewError("Document original asset not found.")
    return dict(row)


def _pages_for_preview(cur: Any, document: Mapping[str, Any]) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT page_number, width_points, height_points, text_content
        FROM document_pages
        WHERE document_id = %s
        ORDER BY page_number
        """,
        (document["id"],),
    )
    rows = [dict(row) for row in cur.fetchall()]
    if rows:
        return rows

    page_count = max(int(document.get("page_count") or 1), 1)
    return [
        {
            "page_number": page_number,
            "width_points": 612,
            "height_points": 792,
            "text_content": "",
        }
        for page_number in range(1, page_count + 1)
    ]


def _generate_page_assets(
    cur: Any,
    storage: ObjectStorage,
    *,
    document: Mapping[str, Any],
    page: Mapping[str, Any],
    job_id: UUID | None,
    created_objects: list[StoredObject],
) -> None:
    page_number = int(page["page_number"])
    thumbnail = _thumbnail_svg(document, page)
    preview = _page_preview_svg(document, page)
    thumbnail_object = storage.store_bytes(
        thumbnail,
        kind="derived",
        role=f"thumbnail-{document['id']}-{page_number}",
    )
    _remember_created(created_objects, thumbnail_object)
    preview_object = storage.store_bytes(
        preview,
        kind="derived",
        role=f"page-preview-{document['id']}-{page_number}",
    )
    _remember_created(created_objects, preview_object)
    metadata = _preview_metadata(document, page_number, job_id)

    thumbnail_asset_id = upsert_current_asset(
        cur,
        document_id=document["id"],
        asset_role="thumbnail",
        page_number=page_number,
        uri=thumbnail_object.uri,
        mime_type=SVG_MIME,
        byte_size=thumbnail_object.byte_size,
        sha256=thumbnail_object.sha256,
        metadata={**metadata, "previewKind": "svg_thumbnail"},
    )
    page_asset_id = upsert_current_asset(
        cur,
        document_id=document["id"],
        asset_role="page_image",
        page_number=page_number,
        uri=preview_object.uri,
        mime_type=SVG_MIME,
        byte_size=preview_object.byte_size,
        sha256=preview_object.sha256,
        metadata={**metadata, "previewKind": "svg_page_preview"},
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
            text_content,
            image_asset_id,
            thumbnail_asset_id,
            metadata_json
          )
        VALUES (%s, %s, %s, %s, 0, NULL, %s, %s, %s, %s::jsonb)
        ON CONFLICT (document_id, page_number) DO UPDATE
        SET image_asset_id = EXCLUDED.image_asset_id,
            thumbnail_asset_id = EXCLUDED.thumbnail_asset_id,
            metadata_json = document_pages.metadata_json || EXCLUDED.metadata_json,
            updated_at = now()
        """,
        (
            document["id"],
            page_number,
            page.get("width_points") or 612,
            page.get("height_points") or 792,
            page.get("text_content") or None,
            page_asset_id,
            thumbnail_asset_id,
            Jsonb(metadata),
        ),
    )


def _preview_metadata(
    document: Mapping[str, Any],
    page_number: int,
    job_id: UUID | None,
) -> dict[str, Any]:
    return {
        "phase": "phase3",
        "previewStatus": "generated",
        "renderer": {
            "name": PREVIEW_RENDERER_NAME,
            "version": PREVIEW_RENDERER_VERSION,
            "format": "svg",
        },
        "source": "original_asset",
        "sourceAssetId": str(document["original_asset_id"]),
        "sourceSha256": document["sha256"],
        "pageNumber": page_number,
        "jobId": str(job_id) if job_id else None,
    }


def _thumbnail_svg(document: Mapping[str, Any], page: Mapping[str, Any]) -> bytes:
    title = _escape_svg(str(document["title"]))
    family = _escape_svg(str(document["document_family"]).replace("_", " ").title())
    page_number = int(page["page_number"])
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
  <text x="38" y="268" font-family="Inter, Arial, sans-serif" font-size="12" fill="#94A3B8">Page {page_number}</text>
</svg>""".encode()


def _page_preview_svg(document: Mapping[str, Any], page: Mapping[str, Any]) -> bytes:
    title = _escape_svg(str(document["title"]))
    filename = _escape_svg(str(document.get("original_filename") or "Original document"))
    sha = str(document.get("sha256") or "")[:12]
    page_number = int(page["page_number"])
    page_text = _escape_svg(str(page.get("text_content") or "")[:220])
    text_line = (
        f'<text x="180" y="925" font-family="Inter, Arial, sans-serif" font-size="16" fill="#64748B">{page_text}</text>'
        if page_text
        else '<text x="180" y="925" font-family="Inter, Arial, sans-serif" font-size="16" fill="#64748B">Canonical parse text is pending or unavailable for this page.</text>'
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="1240" viewBox="0 0 960 1240">
  <rect width="960" height="1240" fill="#F7F9FC"/>
  <rect x="110" y="80" width="740" height="1080" rx="8" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="2"/>
  <rect x="180" y="150" width="600" height="34" rx="3" fill="#E2ECF8"/>
  <text x="180" y="245" font-family="Inter, Arial, sans-serif" font-size="30" font-weight="700" fill="#182235">{title[:42]}</text>
  <text x="180" y="288" font-family="Inter, Arial, sans-serif" font-size="18" fill="#64748B">{filename[:64]}</text>
  <text x="180" y="326" font-family="Inter, Arial, sans-serif" font-size="16" fill="#64748B">Page {page_number} · SHA-256 {sha}</text>
  <rect x="180" y="410" width="600" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="462" width="560" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="514" width="520" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="566" width="480" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="618" width="600" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="670" width="530" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="722" width="560" height="8" rx="4" fill="#CBD5E1"/>
  <rect x="180" y="820" width="520" height="68" rx="7" fill="#EAF3FF" stroke="#2563EB" stroke-width="2"/>
  <text x="210" y="862" font-family="Inter, Arial, sans-serif" font-size="18" font-weight="700" fill="#2563EB">Phase 3 page preview generated</text>
  {text_line}
</svg>""".encode()


def _escape_svg(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _remember_created(objects: list[StoredObject], stored: StoredObject | None) -> None:
    if stored and stored.created:
        objects.append(stored)


def _cleanup_created_objects(objects: list[StoredObject]) -> None:
    for stored in objects:
        cleanup_unreferenced_stored_object(stored)
