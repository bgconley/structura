from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from lib.jobs import create_job_with_cursor


def enqueue_embed_document_job(
    cur: Any,
    *,
    document_id: UUID,
    household_id: UUID | None = None,
    force_reembed: bool = False,
    priority: int = 32,
) -> UUID:
    if household_id is None:
        cur.execute("SELECT household_id FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
        household_id = row["household_id"] if row else None
    job_id = uuid4()
    create_job_with_cursor(
        cur,
        job_id=job_id,
        job_type="embed",
        household_id=household_id,
        document_id=document_id,
        payload={
            "schema_name": "embed_document_job",
            "schema_version": "v1",
            "job_id": str(job_id),
            "created_at": datetime.now(UTC).isoformat(),
            "attempt": 1,
            "priority": priority,
            "document_id": str(document_id),
            "modalities": ["text"],
            "model_profile": "structura-fixture-text-embedding:v1",
            "force_reembed": force_reembed,
        },
        priority=priority,
        queue_name="embeddings",
    )
    return job_id
