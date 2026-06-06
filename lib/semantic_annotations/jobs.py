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
    semantic_quality_mode: str | None = None,
    allow_8b_rescue: bool = False,
    requested_by: str = "system",
    requested_by_user_id: UUID | None = None,
    user_intent_reason: str | None = None,
    priority: int = 34,
    reason: str = "phase8_5.docling_semantic_annotation",
    source_semantic_region_id: UUID | None = None,
    rescue_failure_class: str | None = None,
    dedupe_existing: bool = False,
) -> UUID:
    if quality_mode in {"high_quality", "rescue"} or allow_8b_rescue or rescue_failure_class:
        raise ValueError(
            "Separate high-quality/rescue semantic passes have been removed from "
            "the active runtime. Smart Parse already uses Qwen3-VL-8B FP8."
        )
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
            existing_id = existing["id"]
            return existing_id if isinstance(existing_id, UUID) else UUID(str(existing_id))
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
            semantic_quality_mode=semantic_quality_mode,
            requested_by=requested_by,
            requested_by_user_id=requested_by_user_id,
            user_intent_reason=user_intent_reason,
            reason=reason,
            source_semantic_region_id=source_semantic_region_id,
        ),
        priority=priority,
        queue_name="semantic-annotations",
    )
    return job_id
