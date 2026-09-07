from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from lib.config import Settings, get_settings
from lib.contracts import AcceptedJob
from lib.db.connection import db_connection
from lib.documents.ingestion_content import (
    ALLOWED_UPLOAD_MIME_TYPES as ALLOWED_UPLOAD_MIME_TYPES,
)
from lib.documents.ingestion_content import (
    EXTENSION_MIME_TYPES as EXTENSION_MIME_TYPES,
)
from lib.documents.ingestion_content import (
    UPLOAD_SOURCES,
    safe_original_filename,
    title_from_filename,
    validate_upload_mime,
)
from lib.documents.ingestion_content import (
    parse_hints_json as parse_hints_json,
)
from lib.documents.ingestion_content import (
    sniff_mime as sniff_mime,
)
from lib.documents.ingestion_jobs import create_ingestion_jobs
from lib.documents.ingestion_models import (
    DocumentIngestionError as DocumentIngestionError,
)
from lib.documents.ingestion_models import (
    DocumentIngestionRequest as DocumentIngestionRequest,
)
from lib.documents.ingestion_models import (
    DocumentIngestionResult as DocumentIngestionResult,
)
from lib.documents.ingestion_repository import (
    attach_original_asset,
    create_ingest_batch,
    create_original_document,
    first_duplicate_document,
)
from lib.storage import (
    InvalidObjectUri,
    ObjectStorage,
    StagedObject,
    StorageError,
    StoredObject,
    UploadTooLarge,
    cleanup_unreferenced_stored_object,
    file_sha256,
    lock_content_hash,
)


def ingest_document_stream(
    stream: BinaryIO,
    *,
    request: DocumentIngestionRequest,
    settings: Settings | None = None,
) -> DocumentIngestionResult:
    resolved_settings = settings or get_settings()
    storage = ObjectStorage(settings=resolved_settings)
    staged: StagedObject | None = None
    try:
        staged = storage.stage_stream(
            stream,
            kind="canonical",
            max_bytes=resolved_settings.max_upload_bytes,
        )
        return ingest_staged_document(staged, request=request, storage=storage)
    except UploadTooLarge as exc:
        raise DocumentIngestionError(413, str(exc)) from exc
    finally:
        storage.cleanup_staged(staged)


def ingest_document_path(
    path: Path,
    *,
    request: DocumentIngestionRequest,
    settings: Settings | None = None,
) -> DocumentIngestionResult:
    with path.open("rb") as stream:
        return ingest_document_stream(stream, request=request, settings=settings)


def document_exists_for_sha256(*, household_id: UUID, sha256: str) -> bool:
    with db_connection() as conn, conn.cursor() as cur:
        return first_duplicate_document(cur, household_id=household_id, sha256=sha256) is not None


def source_file_sha256(path: Path) -> str:
    return file_sha256(path)


def ingest_staged_document(
    staged: StagedObject,
    *,
    request: DocumentIngestionRequest,
    storage: ObjectStorage,
) -> DocumentIngestionResult:
    if request.source not in UPLOAD_SOURCES:
        raise DocumentIngestionError(422, "Invalid source")
    if staged.byte_size <= 0:
        raise DocumentIngestionError(422, "Uploaded file is empty")

    original_name = safe_original_filename(request.filename)
    mime_type = validate_upload_mime(
        declared_mime=request.declared_mime_type,
        filename=original_name,
        staged=staged,
    )
    title = (
        request.supplied_title.strip()
        if request.supplied_title and request.supplied_title.strip()
        else title_from_filename(original_name)
    )
    stored_original: StoredObject | None = None
    db_committed = False
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                duplicate_id = first_duplicate_document(
                    cur, household_id=request.household_id, sha256=staged.sha256
                )
                batch_id = create_ingest_batch(
                    cur,
                    source=request.source,
                    original_name=original_name,
                    hints=request.hints or {},
                )
                document_id = create_original_document(
                    cur,
                    request=request,
                    batch_id=batch_id,
                    title=title,
                    original_name=original_name,
                    sha256=staged.sha256,
                    mime_type=mime_type,
                    byte_size=staged.byte_size,
                    duplicate_id=duplicate_id,
                )
                lock_content_hash(cur, staged.sha256)
                stored_original = storage.commit_staged(staged, kind="canonical", role="original")
                asset_id = attach_original_asset(
                    cur,
                    document_id=document_id,
                    stored=stored_original,
                    mime_type=mime_type,
                    original_name=original_name,
                )
                ingest_job = create_ingestion_jobs(
                    cur,
                    household_id=request.household_id,
                    document_id=document_id,
                    batch_id=batch_id,
                    asset_id=asset_id,
                    stored=stored_original,
                    mime_type=mime_type,
                    filename=original_name,
                    source=request.source,
                    hints=request.hints or {},
                    requested_by=request.requested_by,
                    duplicate_id=duplicate_id,
                )
                result = DocumentIngestionResult(
                    accepted_job=AcceptedJob.model_validate(
                        {"jobId": ingest_job.job_id, "status": ingest_job.status}
                    ),
                    document_id=document_id,
                    asset_id=asset_id,
                    sha256=stored_original.sha256,
                )
            conn.commit()
            db_committed = True
    except DocumentIngestionError:
        if not db_committed:
            cleanup_unreferenced_stored_object(stored_original)
        raise
    except (InvalidObjectUri, StorageError, OSError) as exc:
        if not db_committed:
            cleanup_unreferenced_stored_object(stored_original)
        raise DocumentIngestionError(500, str(exc)) from exc
    except Exception:
        if not db_committed:
            cleanup_unreferenced_stored_object(stored_original)
        raise
    return result
