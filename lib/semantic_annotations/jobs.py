from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from lib.jobs import create_job_with_cursor
from lib.jobs.event_payloads import build_semantic_annotate_document_job_payload


def enqueue_semantic_annotation_job(
    cur: Any,
    *,
    document_id: UUID,
    household_id: UUID | None = None,
    quality_mode: str = "smart",
    requested_by: str = "system",
    priority: int = 34,
    reason: str = "phase8_5.docling_semantic_annotation",
    dedupe_existing: bool = False,
) -> UUID:
    if household_id is None:
        cur.execute("SELECT household_id FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
        household_id = row["household_id"] if row else None
    if dedupe_existing:
        cur.execute(
            """
            SELECT id
            FROM pipeline_jobs
            WHERE document_id = %s
              AND job_type = 'semantic_annotate'
              AND queue_name = 'semantic-annotations'
              AND status IN ('queued', 'running')
              AND payload_json ->> 'quality_mode' = %s
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (document_id, quality_mode),
        )
        existing = cur.fetchone()
        if existing:
            return existing["id"]
    job_id = uuid4()
    create_job_with_cursor(
        cur,
        job_id=job_id,
        job_type="semantic_annotate",
        household_id=household_id,
        document_id=document_id,
        payload=build_semantic_annotate_document_job_payload(
            job_id=job_id,
            document_id=document_id,
            quality_mode=quality_mode,
            requested_by=requested_by,
            reason=reason,
        ),
        priority=priority,
        queue_name="semantic-annotations",
    )
    return job_id
