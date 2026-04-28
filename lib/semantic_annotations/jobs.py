from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from lib.jobs import create_job_with_cursor


def enqueue_semantic_annotation_job(
    cur: Any,
    *,
    document_id: UUID,
    household_id: UUID | None = None,
    quality_mode: str = "smart",
    requested_by: str = "system",
    priority: int = 34,
    reason: str = "phase8_5.docling_semantic_annotation",
) -> UUID:
    if household_id is None:
        cur.execute("SELECT household_id FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
        household_id = row["household_id"] if row else None
    job_id = uuid4()
    create_job_with_cursor(
        cur,
        job_id=job_id,
        job_type="semantic_annotate",
        household_id=household_id,
        document_id=document_id,
        payload={
            "schema_name": "semantic_annotate_document_job",
            "schema_version": "v1",
            "job_id": str(job_id),
            "document_id": str(document_id),
            "quality_mode": quality_mode,
            "requested_by": requested_by,
            "reason": reason,
            "created_at": datetime.now(UTC).isoformat(),
        },
        priority=priority,
        queue_name="semantic-annotations",
    )
    return job_id
