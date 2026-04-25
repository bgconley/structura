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

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.config import get_settings
from lib.contracts import AcceptedJob
from lib.db.connection import db_connection
from lib.documents.read_model import (
    DocumentListFilters,
    get_document_detail,
    list_document_summaries,
)
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

    summaries, total = list_document_summaries(
        DocumentListFilters(
            household_id=principal.household_id,
            query_text=q.strip() if q and q.strip() else None,
            family=family.strip() if family and family.strip() else None,
            review_status=reviewStatus.strip() if reviewStatus and reviewStatus.strip() else None,
            folder_id=folderId,
            limit=limit,
            offset=offset,
        )
    )
    return {
        "items": [summary.model_dump(by_alias=True) for summary in summaries],
        "total": total,
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
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    document = get_document_detail(documentId, principal.household_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document.model_dump(by_alias=True)


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
