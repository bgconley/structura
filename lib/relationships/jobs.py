from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from lib.jobs import create_job_with_cursor


def enqueue_relationship_job(
    cur: object,
    *,
    household_id: UUID | None,
    document_id: UUID,
    priority: int = 35,
    reason: str = "phase7.relationship_refresh",
) -> UUID:
    job_id = uuid4()
    create_job_with_cursor(
        cur,
        job_id=job_id,
        job_type="relate",
        household_id=household_id,
        document_id=document_id,
        payload={
            "schema_name": "relate_document_job",
            "schema_version": "v1",
            "job_id": str(job_id),
            "document_id": str(document_id),
            "created_at": datetime.now(UTC).isoformat(),
            "stage": reason,
        },
        priority=priority,
        queue_name="relationships",
    )
    return job_id
