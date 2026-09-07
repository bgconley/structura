from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lib.jobs.errors import JobOwnershipLost, JobServiceError
from lib.jobs.failure_taxonomy import failure_taxonomy_code
from lib.jobs.ownership import JobAttempt, require_owned_job
from lib.jobs.payload_policy import retry_delay_seconds
from lib.jobs.public_errors import safe_job_failure


def claim_job(
    cur: Any,
    *,
    worker_name: str,
    queue_name: str,
    document_id: UUID | None,
    lease_seconds: int,
) -> Mapping[str, Any] | None:
    validate_lease_seconds(lease_seconds)
    recover_expired_running_jobs(cur, queue_name=queue_name, document_id=document_id)
    cur.execute(
        """
        WITH next_job AS (
          SELECT id FROM pipeline_jobs
          WHERE status IN ('queued', 'failed') AND queue_name = %s
            AND (%s::uuid IS NULL OR document_id = %s)
            AND scheduled_at <= clock_timestamp() AND attempt_count < max_attempts
          ORDER BY priority DESC, scheduled_at ASC, created_at ASC
          FOR UPDATE SKIP LOCKED LIMIT 1
        )
        UPDATE pipeline_jobs j
        SET status = 'running', worker_name = %s, claim_token = %s,
            lease_expires_at = clock_timestamp() + (%s * interval '1 second'),
            started_at = COALESCE(started_at, clock_timestamp()),
            attempt_count = attempt_count + 1
        FROM next_job WHERE j.id = next_job.id RETURNING j.*
        """,
        (queue_name, document_id, document_id, worker_name, uuid4(), lease_seconds),
    )
    return cast(Mapping[str, Any] | None, cur.fetchone())


def renew_job(
    cur: Any, *, attempt: JobAttempt, worker_name: str, lease_seconds: int
) -> Mapping[str, Any]:
    validate_lease_seconds(lease_seconds)
    require_owned_job(cur, attempt)
    cur.execute(
        """
        UPDATE pipeline_jobs SET lease_expires_at =
          clock_timestamp() + (%s * interval '1 second')
        WHERE id = %s AND claim_token = %s AND worker_name = %s
        RETURNING *
        """,
        (lease_seconds, attempt.job_id, attempt.claim_token, worker_name),
    )
    row = cur.fetchone()
    if row is None:
        raise JobOwnershipLost("Job attempt worker identity does not match.")
    return cast(Mapping[str, Any], row)


def complete_owned_job(
    cur: Any, *, attempt: JobAttempt, result: Mapping[str, Any] | None
) -> Mapping[str, Any]:
    require_owned_job(cur, attempt)
    cur.execute(
        """
        UPDATE pipeline_jobs
        SET status = 'succeeded', finished_at = clock_timestamp(),
            lease_expires_at = NULL, claim_token = NULL, result_json = %s::jsonb
        WHERE id = %s AND claim_token = %s RETURNING *
        """,
        (Jsonb(dict(result or {})), attempt.job_id, attempt.claim_token),
    )
    return _required_row(cur)


def fail_owned_job(
    cur: Any,
    *,
    attempt: JobAttempt,
    error_class: str,
    message: str,
    retryable: bool,
    suppress: bool,
    details: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    require_owned_job(cur, attempt)
    cur.execute(
        "SELECT *, clock_timestamp() AS failure_time FROM pipeline_jobs WHERE id = %s",
        (attempt.job_id,),
    )
    current = _required_row(cur)
    terminal = current["attempt_count"] >= current["max_attempts"] or not retryable
    status = "dead_letter" if terminal else "failed"
    delay = retry_delay_seconds(current["attempt_count"])
    next_retry_at = current["failure_time"] + timedelta(seconds=delay)
    safe_error = safe_job_failure(error_class=error_class, message=message, details=details)
    error_json = {
        "document_id": str(current["document_id"]) if current["document_id"] else None,
        "stage": current["job_type"],
        "taxonomy_code": safe_error["public_code"],
        "retryable": retryable,
        "retry_action": f"/api/v1/admin/jobs/{attempt.job_id}/retry",
        "retry_after_seconds": None if terminal else delay,
        "next_retry_at": None if terminal else next_retry_at.isoformat(),
        "dismissed_at": None,
        "suppressed": suppress,
        **safe_error,
        "last_error": safe_error["message"],
    }
    cur.execute(
        """
        UPDATE pipeline_jobs
        SET status = %s,
            finished_at = CASE WHEN %s THEN clock_timestamp() ELSE finished_at END,
            lease_expires_at = NULL, claim_token = NULL,
            scheduled_at = CASE WHEN %s THEN scheduled_at
              ELSE clock_timestamp() + (%s * interval '1 second') END,
            error_json = %s::jsonb
        WHERE id = %s AND claim_token = %s RETURNING *
        """,
        (status, terminal, terminal, delay, Jsonb(error_json), attempt.job_id, attempt.claim_token),
    )
    return _required_row(cur)


def validate_lease_seconds(lease_seconds: int) -> None:
    if isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 86400:
        raise JobServiceError("Job lease must be between 1 and 86400 seconds.")


def _required_row(cur: Any) -> Mapping[str, Any]:
    row = cur.fetchone()
    if row is None:
        raise JobServiceError("Job lifecycle update did not return a row.")
    return cast(Mapping[str, Any], row)


def recover_expired_running_jobs(
    cur: Any,
    *,
    queue_name: str,
    document_id: UUID | None,
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
          AND (%s::uuid IS NULL OR document_id = %s)
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at <= clock_timestamp()
        """,
        (taxonomy_code, Jsonb(safe_error), queue_name, document_id, document_id),
    )
    return int(cur.rowcount)
