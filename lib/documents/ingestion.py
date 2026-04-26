from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lib.config import Settings, get_settings
from lib.contracts import AcceptedJob, JobState
from lib.db.connection import db_connection
from lib.jobs import create_job_with_cursor
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


@dataclass(frozen=True)
class DocumentIngestionRequest:
    household_id: UUID
    owner_user_id: UUID
    source: str
    filename: str | None
    declared_mime_type: str | None = None
    supplied_title: str | None = None
    hints: dict[str, object] | None = None
    requested_by: str = "user"


@dataclass(frozen=True)
class DocumentIngestionResult:
    accepted_job: AcceptedJob
    document_id: UUID
    asset_id: UUID
    sha256: str


class DocumentIngestionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def parse_hints_json(hints_json: str | None) -> dict[str, object]:
    if not hints_json:
        return {}
    try:
        parsed = json.loads(hints_json)
    except json.JSONDecodeError as exc:
        raise DocumentIngestionError(422, "hintsJson must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise DocumentIngestionError(422, "hintsJson must encode a JSON object")
    return parsed


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
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM documents
                WHERE household_id = %s
                  AND original_sha256 = %s
                  AND deleted_at IS NULL
                LIMIT 1
                """,
                (household_id, sha256),
            )
            return cur.fetchone() is not None


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
    hints = request.hints or {}
    stored_original: StoredObject | None = None
    db_committed = False
    accepted_job: AcceptedJob | None = None
    document_id: UUID | None = None
    asset_id: UUID | None = None

    try:
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
                    (request.household_id, staged.sha256),
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
                        f"{request.source}:{original_name}",
                        request.source,
                        Jsonb({"source": request.source, "hints": hints}),
                    ),
                )
                batch = cur.fetchone()
                if not batch:
                    raise DocumentIngestionError(500, "Failed to create ingest batch")
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
                        request.household_id,
                        request.owner_user_id,
                        title,
                        original_name,
                        request.source,
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
                                "phase": (
                                    "phase6" if request.source == "watched_folder" else "phase1"
                                ),
                            }
                        ),
                    ),
                )
                document = cur.fetchone()
                if not document:
                    raise DocumentIngestionError(500, "Failed to create document")
                document_id = cast(UUID, document["id"])
                lock_content_hash(cur, staged.sha256)
                stored_original = storage.commit_staged(staged, kind="canonical", role="original")
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
                        stored_original.uri,
                        mime_type,
                        stored_original.byte_size,
                        stored_original.sha256,
                        Jsonb({"originalFilename": original_name, "storage": "content_addressed"}),
                    ),
                )
                asset = cur.fetchone()
                if not asset:
                    raise DocumentIngestionError(500, "Failed to create original asset")
                asset_id = cast(UUID, asset["id"])
                cur.execute(
                    """
                    UPDATE documents
                    SET canonical_asset_id = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (asset_id, document_id),
                )
                ingest_job = _create_pipeline_jobs(
                    cur,
                    household_id=request.household_id,
                    document_id=document_id,
                    batch_id=batch["id"],
                    asset_id=asset_id,
                    stored=stored_original,
                    mime_type=mime_type,
                    filename=original_name,
                    source=request.source,
                    hints=hints,
                    requested_by=request.requested_by,
                    duplicate_id=duplicate["id"] if duplicate else None,
                )
                accepted_job = AcceptedJob.model_validate(
                    {"jobId": ingest_job.job_id, "status": ingest_job.status},
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

    if not accepted_job or not document_id or not asset_id or not stored_original:
        raise DocumentIngestionError(500, "Upload job was not created")
    return DocumentIngestionResult(
        accepted_job=accepted_job,
        document_id=document_id,
        asset_id=asset_id,
        sha256=stored_original.sha256,
    )


def validate_upload_mime(
    *,
    declared_mime: str | None,
    filename: str,
    staged: StagedObject,
) -> str:
    with staged.temp_path.open("rb") as source:
        header = source.read(16)
    sniffed = sniff_mime(header)
    suffix = Path(filename).suffix.lower()
    extension_mime = EXTENSION_MIME_TYPES.get(suffix)
    declared = (declared_mime or "").split(";")[0].strip().lower() or None

    mime_type = sniffed or declared or extension_mime or mimetypes.guess_type(filename)[0]
    if not mime_type or mime_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise DocumentIngestionError(415, "Only PDF and common image uploads are supported")
    if extension_mime and sniffed and extension_mime != sniffed:
        raise DocumentIngestionError(415, "File extension does not match file content")
    return mime_type


def sniff_mime(header: bytes) -> str | None:
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


def safe_original_filename(filename: str | None) -> str:
    candidate = Path(filename or "uploaded-document").name
    candidate = candidate.replace("\r", "").replace("\n", "").strip()
    return candidate or "uploaded-document"


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled document"


def _create_pipeline_jobs(
    cur: object,
    *,
    household_id: UUID,
    document_id: UUID,
    batch_id: UUID,
    asset_id: UUID,
    stored: StoredObject,
    mime_type: str,
    filename: str,
    source: str,
    hints: dict[str, object],
    requested_by: str,
    duplicate_id: UUID | None,
) -> JobState:
    ingest_job_id = uuid4()
    ingest_payload = {
        "schema_name": "ingest_document_job",
        "schema_version": "v1",
        "job_id": str(ingest_job_id),
        "created_at": datetime.now(UTC).isoformat(),
        "attempt": 1,
        "priority": 5,
        "requested_by": requested_by,
        "source": source,
        "input_object": {
            "uri": stored.uri,
            "sha256": stored.sha256,
            "mime_type": mime_type,
            "filename": filename,
            "size_bytes": stored.byte_size,
        },
        "ingest_batch_id": str(batch_id),
        "document_id": str(document_id),
        "asset_id": str(asset_id),
        "user_supplied_hints": hints,
        "metadata": {
            "duplicate_document_id": str(duplicate_id) if duplicate_id else None,
        },
    }
    ingest_job = create_job_with_cursor(
        cur,
        job_id=ingest_job_id,
        job_type="ingest",
        household_id=household_id,
        document_id=document_id,
        batch_id=batch_id,
        payload=ingest_payload,
        priority=50,
        queue_name="ingest",
    )
    preview_job_id = uuid4()
    create_job_with_cursor(
        cur,
        job_id=preview_job_id,
        job_type="preview",
        household_id=household_id,
        document_id=document_id,
        batch_id=batch_id,
        payload={
            "job_id": str(preview_job_id),
            "document_id": str(document_id),
            "asset_id": str(asset_id),
            "stage": "phase1.preview",
        },
        priority=45,
        queue_name="previews",
    )
    docling_job_id = uuid4()
    create_job_with_cursor(
        cur,
        job_id=docling_job_id,
        job_type="docling_convert",
        household_id=household_id,
        document_id=document_id,
        batch_id=batch_id,
        payload={
            "job_id": str(docling_job_id),
            "document_id": str(document_id),
            "asset_id": str(asset_id),
            "stage": "phase3.docling_convert",
            "input_object": {
                "sha256": stored.sha256,
                "mime_type": mime_type,
                "filename": filename,
                "size_bytes": stored.byte_size,
            },
        },
        priority=40,
        queue_name="docling",
    )
    return ingest_job
