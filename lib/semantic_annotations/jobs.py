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
    if quality_mode in {"high_quality", "rescue"} or allow_8b_rescue:
        raise ValueError(
            "Separate high-quality/rescue semantic passes have been removed from "
            "the active runtime. Smart Parse already uses Qwen3-VL-8B FP8."
        )
    if household_id is None:
        cur.execute("SELECT household_id FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
        household_id = row["household_id"] if row else None
    if dedupe_existing:
        if quality_mode == "rescue" and source_semantic_region_id is not None:
            cur.execute(
                """
                SELECT id
                FROM pipeline_jobs
                WHERE document_id = %s
                  AND job_type = 'semantic_annotate'
                  AND queue_name = 'semantic-annotations'
                  AND status IN ('queued', 'running', 'succeeded')
                  AND payload_json ->> 'quality_mode' = 'rescue'
                  AND payload_json ->> 'source_semantic_region_id' = %s
                  AND COALESCE(payload_json #>> '{metadata,failure_class}', '') = %s
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (
                    document_id,
                    str(source_semantic_region_id),
                    rescue_failure_class or "",
                ),
            )
            existing = cur.fetchone()
            if existing:
                existing_id = existing["id"]
                return existing_id if isinstance(existing_id, UUID) else UUID(str(existing_id))
            cur.execute(
                """
                SELECT id
                FROM pipeline_jobs
                WHERE document_id = %s
                  AND job_type = 'semantic_annotate'
                  AND queue_name = 'semantic-annotations'
                  AND status = 'succeeded'
                  AND payload_json ->> 'quality_mode' = 'rescue'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (document_id,),
            )
            existing = cur.fetchone()
            if existing:
                existing_id = existing["id"]
                return existing_id if isinstance(existing_id, UUID) else UUID(str(existing_id))
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
    metadata = {"failure_class": rescue_failure_class} if rescue_failure_class else None
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
            allow_8b_rescue=allow_8b_rescue,
            requested_by=requested_by,
            requested_by_user_id=requested_by_user_id,
            user_intent_reason=user_intent_reason,
            reason=reason,
            source_semantic_region_id=source_semantic_region_id,
            metadata=metadata,
        ),
        priority=priority,
        queue_name="semantic-annotations",
    )
    return job_id
