from __future__ import annotations

import json
import mimetypes
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from psycopg.types.json import Jsonb
from starlette.responses import FileResponse

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.config import get_settings
from lib.contracts import AcceptedJob, DocumentAsset, DocumentDetail, DocumentPage, DocumentSummary
from lib.db.connection import db_connection
from lib.jobs import JobService, create_job_with_cursor
from lib.storage import (
    InvalidObjectUri,
    ObjectStorage,
    StagedObject,
    StorageError,
    StoredObject,
    UploadTooLarge,
)
from workers.previews import PreviewError, generate_phase1_preview

router = APIRouter(prefix="/api/v1", tags=["Documents"])

ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
EXTENSION_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}
UPLOAD_SOURCES = {
    "web_upload",
    "api_upload",
    "mobile_scan",
    "watched_folder",
    "email_import",
    "bulk_import",
}

DOCUMENT_LIST_COUNT_SQL = """
SELECT count(*) AS total
FROM documents d
LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
WHERE d.deleted_at IS NULL
  AND d.household_id = %s
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
      SELECT array_agg(COALESCE(f.path_cache, '/' || f.name) ORDER BY f.name)
      FROM document_folder_memberships dfm
      JOIN folders f ON f.id = dfm.folder_id
      WHERE dfm.document_id = d.id
    ),
    ARRAY[]::text[]
  ) AS folder_paths
FROM documents d
LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
WHERE d.deleted_at IS NULL
  AND d.household_id = %s
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


@router.get("/documents")
def list_documents(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    q: str | None = None,
    family: str | None = None,
    reviewStatus: str | None = None,
    folderId: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")

    query_text = q.strip() if q and q.strip() else None
    query_like = f"%{query_text}%" if query_text else None
    family_filter = family.strip() if family and family.strip() else None
    review_filter = reviewStatus.strip() if reviewStatus and reviewStatus.strip() else None
    folder_filter = folderId if folderId else None
    filter_params: list[object] = [
        principal.household_id,
        query_text,
        query_like,
        query_like,
        query_like,
        family_filter,
        family_filter,
        review_filter,
        review_filter,
        folder_filter,
        folder_filter,
    ]

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                DOCUMENT_LIST_COUNT_SQL,
                filter_params,
            )
            total_row = cur.fetchone()
            cur.execute(
                DOCUMENT_LIST_SELECT_SQL,
                [*filter_params, limit, offset],
            )
            rows = cur.fetchall()

    return {
        "items": [_document_summary_from_row(row).model_dump(by_alias=True) for row in rows],
        "total": int(total_row["total"] if total_row else 0),
    }


@router.post(
    "/documents",
    response_model=AcceptedJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_document(
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    suppliedTitle: Annotated[str | None, Form()] = None,
    hintsJson: Annotated[str | None, Form()] = None,
) -> AcceptedJob:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")
    if source not in UPLOAD_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid source",
        )

    hints = _parse_hints_json(hintsJson)
    settings = get_settings()
    storage = ObjectStorage(settings=settings)
    staged: StagedObject | None = None
    stored_original: StoredObject | None = None
    db_committed = False
    document_id: UUID | None = None
    preview_job_id: UUID | None = None
    accepted_job: AcceptedJob | None = None
    try:
        staged = storage.stage_stream(
            file.file,
            kind="canonical",
            max_bytes=settings.max_upload_bytes,
        )
        if staged.byte_size <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Uploaded file is empty",
            )
        original_name = _safe_original_filename(file.filename)
        mime_type = _validate_upload_mime(
            declared_mime=file.content_type,
            filename=original_name,
            staged=staged,
        )
        title = (
            suppliedTitle.strip()
            if suppliedTitle and suppliedTitle.strip()
            else _title_from_filename(original_name)
        )

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM documents
                    WHERE household_id = %s
                      AND original_sha256 = %s
                      AND deleted_at IS NULL
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (principal.household_id, staged.sha256),
                )
                duplicate = cur.fetchone()
                cur.execute(
                    """
                    INSERT INTO ingest_batches
                      (
                        label,
                        source,
                        status,
                        file_count_expected,
                        file_count_received,
                        metadata_json
                      )
                    VALUES (%s, %s, 'open', 1, 1, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        f"{source}:{original_name}",
                        source,
                        Jsonb({"source": source, "hints": hints}),
                    ),
                )
                batch = cur.fetchone()
                if not batch:
                    raise HTTPException(status_code=500, detail="Failed to create ingest batch")
                cur.execute(
                    """
                    INSERT INTO documents
                      (
                        batch_id,
                        household_id,
                        owner_user_id,
                        title,
                        original_filename,
                        ingestion_source,
                        original_sha256,
                        duplicate_of_document_id,
                        received_at,
                        metadata_json
                      )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s::jsonb)
                    RETURNING id
                    """,
                    (
                        batch["id"],
                        principal.household_id,
                        principal.user_id,
                        title,
                        original_name,
                        source,
                        staged.sha256,
                        duplicate["id"] if duplicate else None,
                        Jsonb(
                            {
                                "upload": {
                                    "mimeType": mime_type,
                                    "sizeBytes": staged.byte_size,
                                    "duplicateSuspect": duplicate is not None,
                                },
                                "hints": hints,
                                "phase": "phase1",
                            }
                        ),
                    ),
                )
                document = cur.fetchone()
                if not document:
                    raise HTTPException(status_code=500, detail="Failed to create document")
                document_id = document["id"]
                stored = storage.commit_staged(staged, kind="canonical", role="original")
                stored_original = stored
                staged = None
                cur.execute(
                    """
                    INSERT INTO document_assets
                      (
                        document_id,
                        asset_role,
                        uri,
                        mime_type,
                        byte_size,
                        sha256,
                        metadata_json
                      )
                    VALUES (%s, 'original', %s, %s, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        document_id,
                        stored.uri,
                        mime_type,
                        stored.byte_size,
                        stored.sha256,
                        Jsonb({"originalFilename": original_name, "storage": "content_addressed"}),
                    ),
                )
                asset = cur.fetchone()
                if not asset:
                    raise HTTPException(status_code=500, detail="Failed to create original asset")
                cur.execute(
                    """
                    UPDATE documents
                    SET canonical_asset_id = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (asset["id"], document_id),
                )
                ingest_job_id = uuid4()
                ingest_payload = {
                    "schema_name": "ingest_document_job",
                    "schema_version": "v1",
                    "job_id": str(ingest_job_id),
                    "created_at": datetime.now(UTC).isoformat(),
                    "attempt": 1,
                    "priority": 5,
                    "requested_by": "user",
                    "source": source,
                    "input_object": {
                        "uri": stored.uri,
                        "sha256": stored.sha256,
                        "mime_type": mime_type,
                        "filename": original_name,
                        "size_bytes": stored.byte_size,
                    },
                    "ingest_batch_id": str(batch["id"]),
                    "document_id": str(document_id),
                    "asset_id": str(asset["id"]),
                    "user_supplied_hints": hints,
                    "metadata": {
                        "duplicate_document_id": str(duplicate["id"]) if duplicate else None,
                    },
                }
                ingest_job = create_job_with_cursor(
                    cur,
                    job_id=ingest_job_id,
                    job_type="ingest",
                    document_id=document_id,
                    batch_id=batch["id"],
                    payload=ingest_payload,
                    priority=50,
                    queue_name="ingest",
                )
                accepted_job = AcceptedJob.model_validate(
                    {"jobId": ingest_job.job_id, "status": ingest_job.status},
                )
                preview_job_id = uuid4()
                create_job_with_cursor(
                    cur,
                    job_id=preview_job_id,
                    job_type="preview",
                    document_id=document_id,
                    batch_id=batch["id"],
                    payload={
                        "job_id": str(preview_job_id),
                        "document_id": str(document_id),
                        "asset_id": str(asset["id"]),
                        "stage": "phase1.preview",
                    },
                    priority=45,
                    queue_name="previews",
                )
            conn.commit()
            db_committed = True
    except UploadTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except HTTPException:
        if not db_committed:
            _cleanup_unreferenced_stored_object(stored_original)
        raise
    except (InvalidObjectUri, StorageError, OSError) as exc:
        if not db_committed:
            _cleanup_unreferenced_stored_object(stored_original)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    except Exception:
        if not db_committed:
            _cleanup_unreferenced_stored_object(stored_original)
        raise
    finally:
        storage.cleanup_staged(staged)

    if document_id and preview_job_id:
        try:
            generate_phase1_preview(document_id, storage=storage)
            JobService().complete_job(
                job_id=preview_job_id,
                result={"preview_status": "fallback_generated"},
            )
        except (PreviewError, StorageError, OSError) as exc:
            JobService().fail_job(
                job_id=preview_job_id,
                error_class=exc.__class__.__name__,
                message="Phase 1 preview generation failed",
                retryable=True,
                suppress=True,
            )

    if not accepted_job:
        raise HTTPException(status_code=500, detail="Upload job was not created")
    return accepted_job


@router.get("/documents/{documentId}")
def get_document(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> dict[str, object]:
    document = _get_document_detail(documentId, principal)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document.model_dump(by_alias=True)


@router.get("/assets/{assetId}", tags=["Assets"])
def get_asset(
    assetId: UUID,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> FileResponse:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  a.id,
                  a.asset_role::text AS asset_role,
                  a.uri,
                  a.mime_type,
                  a.byte_size,
                  a.sha256,
                  d.original_filename,
                  d.title
                FROM document_assets a
                JOIN documents d ON d.id = a.document_id
                WHERE a.id = %s
                  AND d.household_id = %s
                  AND d.deleted_at IS NULL
                """,
                (assetId, principal.household_id),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    storage = ObjectStorage()
    try:
        consistency = storage.verify(
            uri=row["uri"],
            expected_sha256=row["sha256"],
            expected_size=row["byte_size"],
        )
        path = storage.path_for_uri(row["uri"])
    except (InvalidObjectUri, StorageError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        ) from None

    if not consistency.ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    filename = _download_filename(
        role=row["asset_role"],
        original_filename=row["original_filename"],
        title=row["title"],
        mime_type=row["mime_type"],
    )
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(
        path,
        media_type=row["mime_type"] or "application/octet-stream",
        filename=filename,
        content_disposition_type="inline",
        headers=headers,
    )


@router.get("/folders", tags=["Organization"])
def list_folders(_principal: Annotated[object, Depends(current_principal)]) -> dict[str, object]:
    return {"items": []}


@router.post("/folders", tags=["Organization"], status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_folder(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Folder management is implemented in Phase 2.",
    )


@router.get("/tags", tags=["Organization"])
def list_tags(_principal: Annotated[object, Depends(current_principal)]) -> dict[str, object]:
    return {"items": []}


@router.post("/tags", tags=["Organization"], status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_tag(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Tag management is implemented in Phase 2.",
    )


@router.post(
    "/documents/{documentId}/organization",
    tags=["Organization"],
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def update_document_organization(
    documentId: UUID,
    _principal: Annotated[object, Depends(require_csrf)],
) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Document organization is implemented in Phase 2.",
    )


@router.get("/relationships", tags=["Relationships"])
def list_relationships(
    _principal: Annotated[object, Depends(current_principal)],
    documentId: UUID | None = None,
) -> dict[str, object]:
    return {"items": []}


@router.post(
    "/relationships",
    tags=["Relationships"],
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def create_relationship(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Document relationships are implemented in Phase 7.",
    )


@router.get("/contacts", tags=["Organization"])
def list_contacts(
    _principal: Annotated[object, Depends(current_principal)],
    q: str | None = None,
) -> dict[str, object]:
    return {"items": []}


@router.post("/contacts", tags=["Organization"], status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_contact(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Contact management is implemented in Phase 6.",
    )


@router.get("/filing-rules", tags=["Automation"])
def list_filing_rules(
    _principal: Annotated[object, Depends(current_principal)],
) -> dict[str, object]:
    return {"items": []}


@router.post(
    "/filing-rules",
    tags=["Automation"],
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def create_filing_rule(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Filing rules are implemented in Phase 6.",
    )


@router.get("/watched-folders", tags=["Automation"])
def list_watched_folders(
    _principal: Annotated[object, Depends(current_principal)],
) -> dict[str, object]:
    return {"items": []}


@router.post(
    "/watched-folders",
    tags=["Automation"],
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def create_watched_folder(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Watched folders are implemented in Phase 6.",
    )


@router.post("/search", tags=["Search"], status_code=status.HTTP_501_NOT_IMPLEMENTED)
def search_documents(_principal: Annotated[object, Depends(current_principal)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Search is implemented in Phase 5.",
    )


@router.get("/review-tasks", tags=["Review"])
def list_review_tasks(
    _principal: Annotated[object, Depends(current_principal)],
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, object]:
    return {"items": []}


@router.post(
    "/documents/{documentId}/review-actions",
    tags=["Review"],
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def create_review_action(
    documentId: UUID,
    _principal: Annotated[object, Depends(require_csrf)],
) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Review actions are implemented in Phase 4.",
    )


@router.get("/documents/{documentId}/field-candidates", tags=["Review"])
def list_field_candidates(
    documentId: UUID,
    _principal: Annotated[object, Depends(current_principal)],
    fieldPath: str | None = None,
) -> dict[str, object]:
    return {"items": []}


@router.get("/documents/{documentId}/canonical-fields", tags=["Review"])
def list_canonical_fields(
    documentId: UUID,
    _principal: Annotated[object, Depends(current_principal)],
) -> dict[str, object]:
    return {"items": []}


@router.post(
    "/documents/{documentId}/canonical-fields",
    tags=["Review"],
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
def create_canonical_field(
    documentId: UUID,
    _principal: Annotated[object, Depends(require_csrf)],
) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Canonical fields are implemented in Phase 4.",
    )


@router.post("/analysis-notes", tags=["Analysis"], status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_analysis_note(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Analysis notes are implemented in Phase 9.",
    )


@router.post("/exports", tags=["Exports"], status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_export(_principal: Annotated[object, Depends(require_csrf)]) -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Exports are implemented in Phase 10.",
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
        }
    )


def _cleanup_unreferenced_stored_object(stored: StoredObject | None) -> None:
    if not stored or not stored.created:
        return
    with suppress(OSError):
        stored.path.unlink(missing_ok=True)
        _remove_empty_storage_dirs(stored.path)


def _remove_empty_storage_dirs(path: Path) -> None:
    for candidate in (path.parent, path.parent.parent, path.parent.parent.parent):
        with suppress(OSError):
            candidate.rmdir()


def _get_document_detail(document_id: UUID, principal: AuthPrincipal) -> DocumentDetail | None:
    if not principal.household_id:
        return None
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
                      SELECT array_agg(COALESCE(f.path_cache, '/' || f.name) ORDER BY f.name)
                      FROM document_folder_memberships dfm
                      JOIN folders f ON f.id = dfm.folder_id
                      WHERE dfm.document_id = d.id
                    ),
                    ARRAY[]::text[]
                  ) AS folder_paths,
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
                  AND d.household_id = %s
                  AND d.deleted_at IS NULL
                """,
                (document_id, principal.household_id),
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
        }
    )


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


def _parse_hints_json(hints_json: str | None) -> dict[str, object]:
    if not hints_json:
        return {}
    try:
        parsed = json.loads(hints_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="hintsJson must be valid JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="hintsJson must encode a JSON object",
        )
    return parsed


def _validate_upload_mime(
    *,
    declared_mime: str | None,
    filename: str,
    staged: StagedObject,
) -> str:
    with staged.temp_path.open("rb") as source:
        header = source.read(16)
    sniffed = _sniff_mime(header)
    suffix = Path(filename).suffix.lower()
    extension_mime = EXTENSION_MIME_TYPES.get(suffix)
    declared = (declared_mime or "").split(";")[0].strip().lower() or None

    mime_type = sniffed or declared or extension_mime or mimetypes.guess_type(filename)[0]
    if not mime_type or mime_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF and common image uploads are supported in Phase 1",
        )
    if extension_mime and sniffed and extension_mime != sniffed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File extension does not match file content",
        )
    return mime_type


def _sniff_mime(header: bytes) -> str | None:
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def _safe_original_filename(filename: str | None) -> str:
    candidate = Path(filename or "uploaded-document").name
    candidate = candidate.replace("\r", "").replace("\n", "").strip()
    return candidate or "uploaded-document"


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled document"


def _download_filename(
    *,
    role: str,
    original_filename: str | None,
    title: str,
    mime_type: str | None,
) -> str:
    if role == "original" and original_filename:
        return _safe_original_filename(original_filename)
    suffix = mimetypes.guess_extension(mime_type or "") or ".bin"
    safe_title = "".join(ch if ch.isalnum() else "-" for ch in title.lower()).strip("-")
    return f"{safe_title or 'structura-document'}-{role}{suffix}"
