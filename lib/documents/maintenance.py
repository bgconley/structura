from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from lib.db.connection import db_connection
from lib.jobs import create_job_with_cursor
from lib.search.jobs import enqueue_embed_document_job


class DocumentMaintenanceError(Exception):
    pass


@dataclass(frozen=True)
class EnqueuedMaintenanceJobs:
    document_id: UUID
    job_ids: list[UUID]


def enqueue_document_reprocess(
    document_id: UUID,
    *,
    requested_by: str = "operator",
) -> EnqueuedMaintenanceJobs:
    """Queue the normal document processing path without mutating parse/extraction tables."""
    with db_connection() as conn:
        with conn.cursor() as cur:
            row = _document_original_asset(cur, document_id)
            preview_job_id = _enqueue_preview(cur, row, requested_by=requested_by)
            docling_job_id = _enqueue_docling(cur, row, requested_by=requested_by)
        conn.commit()
    return EnqueuedMaintenanceJobs(
        document_id=document_id, job_ids=[preview_job_id, docling_job_id]
    )


def enqueue_search_projection_rebuild(
    document_id: UUID,
    *,
    force_reembed: bool = True,
) -> EnqueuedMaintenanceJobs:
    """Queue the embedding worker, which refreshes lexical projection before embedding."""
    with db_connection() as conn:
        with conn.cursor() as cur:
            row = _document_original_asset(cur, document_id)
            job_id = enqueue_embed_document_job(
                cur,
                document_id=document_id,
                household_id=row["household_id"],
                force_reembed=force_reembed,
                priority=34,
            )
        conn.commit()
    return EnqueuedMaintenanceJobs(document_id=document_id, job_ids=[job_id])


def _document_original_asset(cur: Any, document_id: UUID) -> dict[str, Any]:
    cur.execute(
        """
        SELECT
          d.id AS document_id,
          d.household_id,
          d.batch_id,
          d.original_filename,
          da.id AS asset_id,
          da.sha256,
          da.mime_type,
          da.byte_size
        FROM documents d
        JOIN document_assets da ON da.id = d.canonical_asset_id
        WHERE d.id = %s
          AND d.deleted_at IS NULL
          AND da.asset_role = 'original'
          AND da.is_current
        """,
        (document_id,),
    )
    row = cur.fetchone()
    if not row:
        raise DocumentMaintenanceError("Document or current original asset not found.")
    return dict(row)


def _enqueue_preview(
    cur: Any,
    row: dict[str, Any],
    *,
    requested_by: str,
) -> UUID:
    job_id = uuid4()
    create_job_with_cursor(
        cur,
        job_id=job_id,
        job_type="preview",
        household_id=row["household_id"],
        document_id=row["document_id"],
        batch_id=row.get("batch_id"),
        payload={
            "job_id": str(job_id),
            "document_id": str(row["document_id"]),
            "asset_id": str(row["asset_id"]),
            "stage": "phase6.operator_reprocess.preview",
            "requested_by": requested_by,
            "created_at": datetime.now(UTC).isoformat(),
        },
        priority=45,
        queue_name="previews",
    )
    return job_id


def _enqueue_docling(
    cur: Any,
    row: dict[str, Any],
    *,
    requested_by: str,
) -> UUID:
    job_id = uuid4()
    create_job_with_cursor(
        cur,
        job_id=job_id,
        job_type="docling_convert",
        household_id=row["household_id"],
        document_id=row["document_id"],
        batch_id=row.get("batch_id"),
        payload={
            "job_id": str(job_id),
            "document_id": str(row["document_id"]),
            "asset_id": str(row["asset_id"]),
            "stage": "phase6.operator_reprocess.docling_convert",
            "requested_by": requested_by,
            "created_at": datetime.now(UTC).isoformat(),
            "input_object": {
                "sha256": row["sha256"],
                "mime_type": row.get("mime_type"),
                "filename": row.get("original_filename"),
                "size_bytes": row.get("byte_size"),
            },
        },
        priority=40,
        queue_name="docling",
    )
    return job_id
