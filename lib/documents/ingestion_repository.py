"""Original document records in the caller's intake transaction."""

from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.documents.ingestion_models import DocumentIngestionError, DocumentIngestionRequest
from lib.storage import StoredObject


def first_duplicate_document(cur: Any, *, household_id: UUID, sha256: str) -> UUID | None:
    cur.execute(
        """SELECT id FROM documents
        WHERE household_id=%s AND original_sha256=%s AND deleted_at IS NULL
        ORDER BY created_at ASC LIMIT 1""",
        (household_id, sha256),
    )
    row = cur.fetchone()
    return cast(UUID, row["id"]) if row else None


def create_ingest_batch(
    cur: Any, *, source: str, original_name: str, hints: dict[str, object]
) -> UUID:
    cur.execute(
        """INSERT INTO ingest_batches
        (label,source,status,file_count_expected,file_count_received,metadata_json)
        VALUES (%s,%s,'open',1,1,%s::jsonb) RETURNING id""",
        (f"{source}:{original_name}", source, Jsonb({"source": source, "hints": hints})),
    )
    row = cur.fetchone()
    if not row:
        raise DocumentIngestionError(500, "Failed to create ingest batch")
    return cast(UUID, row["id"])


def create_original_document(
    cur: Any,
    *,
    request: DocumentIngestionRequest,
    batch_id: UUID,
    title: str,
    original_name: str,
    sha256: str,
    mime_type: str,
    byte_size: int,
    duplicate_id: UUID | None,
) -> UUID:
    cur.execute(
        """INSERT INTO documents
        (batch_id,household_id,owner_user_id,title,original_filename,ingestion_source,
         original_sha256,duplicate_of_document_id,received_at,metadata_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),%s::jsonb) RETURNING id""",
        (
            batch_id,
            request.household_id,
            request.owner_user_id,
            title,
            original_name,
            request.source,
            sha256,
            duplicate_id,
            Jsonb(
                {
                    "upload": {
                        "mimeType": mime_type,
                        "sizeBytes": byte_size,
                        "duplicateSuspect": duplicate_id is not None,
                    },
                    "hints": request.hints or {},
                    "phase": "phase6" if request.source == "watched_folder" else "phase1",
                }
            ),
        ),
    )
    row = cur.fetchone()
    if not row:
        raise DocumentIngestionError(500, "Failed to create document")
    return cast(UUID, row["id"])


def attach_original_asset(
    cur: Any,
    *,
    document_id: UUID,
    stored: StoredObject,
    mime_type: str,
    original_name: str,
) -> UUID:
    cur.execute(
        """INSERT INTO document_assets
        (document_id,asset_role,uri,mime_type,byte_size,sha256,metadata_json)
        VALUES (%s,'original',%s,%s,%s,%s,%s::jsonb) RETURNING id""",
        (
            document_id,
            stored.uri,
            mime_type,
            stored.byte_size,
            stored.sha256,
            Jsonb({"originalFilename": original_name, "storage": "content_addressed"}),
        ),
    )
    row = cur.fetchone()
    if not row:
        raise DocumentIngestionError(500, "Failed to create original asset")
    asset_id = cast(UUID, row["id"])
    cur.execute(
        "UPDATE documents SET canonical_asset_id=%s,updated_at=now() WHERE id=%s",
        (asset_id, document_id),
    )
    return asset_id
