"""Queue creation inside the new document's original-acceptance transaction."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from lib.contracts import JobState
from lib.jobs import create_job_with_cursor
from lib.relationships.jobs import enqueue_relationship_job
from lib.storage import StoredObject


def create_ingestion_jobs(
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
    enqueue_relationship_job(
        cur,
        household_id=household_id,
        document_id=document_id,
        priority=30,
        reason="phase7.upload_relationship_refresh",
    )
    return ingest_job
