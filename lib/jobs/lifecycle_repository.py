from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.jobs.claim_repository import claim_runnable_job
from lib.jobs.errors import JobOwnershipLost, JobServiceError
from lib.jobs.lineage_repository import revoke_descendants
from lib.jobs.ownership import JobAttempt, require_owned_job
from lib.jobs.payload_policy import retry_delay_seconds
from lib.jobs.public_errors import safe_job_failure
from lib.jobs.recovery_repository import (
    recover_expired_running_jobs as recover_expired_running_jobs,
)


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
    return claim_runnable_job(
        cur,
        worker_name=worker_name,
        queue_name=queue_name,
        document_id=document_id,
        lease_seconds=lease_seconds,
    )


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
    row = _required_row(cur)
    revoke_descendants(cur, attempt.job_id)
    return row


def validate_lease_seconds(lease_seconds: int) -> None:
    if isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 86400:
        raise JobServiceError("Job lease must be between 1 and 86400 seconds.")


def _required_row(cur: Any) -> Mapping[str, Any]:
    row = cur.fetchone()
    if row is None:
        raise JobServiceError("Job lifecycle update did not return a row.")
    return cast(Mapping[str, Any], row)
