from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.jobs.failure_taxonomy import failure_taxonomy_code
from lib.jobs.lineage_repository import lock_job_lineage, revoke_descendants
from lib.jobs.public_errors import safe_job_failure


def recover_expired_running_jobs(cur: Any, *, queue_name: str, document_id: UUID | None) -> int:
    cur.execute(
        "SELECT id FROM pipeline_jobs WHERE queue_name = %s AND status = 'running' "
        "AND (%s::uuid IS NULL OR document_id = %s) "
        "AND lease_expires_at <= clock_timestamp() ORDER BY id LIMIT 128",
        (queue_name, document_id, document_id),
    )
    candidates = cur.fetchall()
    recovered = 0
    for candidate in candidates:
        lineage = lock_job_lineage(cur, candidate["id"], wait=False)
        if lineage is None:
            continue
        cur.execute(
            "SELECT id FROM pipeline_jobs WHERE id = %s FOR UPDATE SKIP LOCKED", (candidate["id"],)
        )
        if cur.fetchone() is None:
            continue
        count = recover_expired_job(cur, queue_name=queue_name, job_id=candidate["id"])
        if count:
            revoke_descendants(cur, candidate["id"])
        recovered += count
    return recovered


def recover_expired_job(
    cur: Any,
    *,
    queue_name: str,
    job_id: UUID,
) -> int:
    taxonomy_code = failure_taxonomy_code(
        queue_name=queue_name
        if queue_name
        in {
            "ingest",
            "previews",
            "docling",
            "semantic-annotations",
            "extraction",
            "embeddings",
            "visual-embeddings",
            "relationships",
        }
        else "pipeline_job",
        job_type="worker_lease",
        error_class="WorkerLeaseExpired",
        details=None,
    )
    safe_error = safe_job_failure("WorkerLeaseExpired", "")
    # One recovery statement may affect many jobs; each event needs its own ID.
    safe_error.pop("error_id")
    cur.execute(
        """
        UPDATE pipeline_jobs
        SET status = CASE
              WHEN attempt_count >= max_attempts THEN 'dead_letter'::job_status_enum
              ELSE 'failed'::job_status_enum
            END,
            worker_name = NULL,
            started_at = CASE
              WHEN attempt_count >= max_attempts THEN started_at
              ELSE NULL
            END,
            lease_expires_at = NULL,
            claim_token = NULL,
            scheduled_at = CASE
              WHEN attempt_count >= max_attempts THEN scheduled_at
              ELSE clock_timestamp()
            END,
            finished_at = CASE
              WHEN attempt_count >= max_attempts THEN clock_timestamp()
              ELSE finished_at
            END,
            error_json = jsonb_strip_nulls(
              jsonb_build_object(
                'taxonomy_code', %s::text,
                'error_id', gen_random_uuid()::text,
                'retryable', attempt_count < max_attempts,
                'retry_action',
                CASE
                  WHEN attempt_count >= max_attempts THEN '/api/v1/admin/jobs/' || id || '/retry'
                  ELSE NULL
                END
              ) || %s::jsonb
            )
        WHERE status = 'running'
          AND queue_name = %s
          AND id = %s
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at <= clock_timestamp()
        """,
        (taxonomy_code, Jsonb(safe_error), queue_name, job_id),
    )
    return int(cur.rowcount)
