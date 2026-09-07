from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lib.contracts import AcceptedJob, JobState
from lib.db.connection import db_connection
from lib.jobs.errors import JobServiceError
from lib.jobs.errors import PayloadSafetyError as PayloadSafetyError
from lib.jobs.lifecycle_repository import (
    claim_job,
    complete_owned_job,
    fail_owned_job,
    renew_job,
)
from lib.jobs.models import BulkCancelResult, ClaimedJob
from lib.jobs.models import QueueTransportProfile as QueueTransportProfile
from lib.jobs.ownership import JobAttempt, fence_current_job
from lib.jobs.payload_policy import queue_transport_profile, sanitize_job_payload
from lib.jobs.payload_policy import retry_delay_seconds as retry_delay_seconds
from lib.jobs.public_errors import safe_job_failure
from lib.jobs.row_mapping import claimed_job_from_row, job_state_from_row


def create_job_with_cursor(
    cur: Any,
    *,
    job_id: UUID,
    job_type: str,
    household_id: UUID | None = None,
    document_id: UUID | None = None,
    batch_id: UUID | None = None,
    payload: Mapping[str, Any] | None = None,
    priority: int = 50,
    queue_name: str = "default",
    max_attempts: int = 5,
) -> JobState:
    safe_payload = sanitize_job_payload(payload or {})
    cur.execute(
        """
        INSERT INTO pipeline_jobs
          (
            id,
            household_id,
            job_type,
            document_id,
            batch_id,
            payload_json,
            priority,
            queue_name,
            max_attempts
          )
          VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        RETURNING *
        """,
        (
            job_id,
            household_id,
            job_type,
            document_id,
            batch_id,
            Jsonb(safe_payload),
            priority,
            queue_name,
            max_attempts,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise JobServiceError("Job was not created.")
    return job_state_from_row(row)


class JobService:
    def __init__(self, *, queue_transport: str | None = None) -> None:
        self.queue_transport = queue_transport_profile(queue_transport)

    def create_job(
        self,
        *,
        job_id: UUID | None = None,
        job_type: str,
        household_id: UUID | None = None,
        document_id: UUID | None = None,
        batch_id: UUID | None = None,
        payload: Mapping[str, Any] | None = None,
        priority: int = 50,
        queue_name: str = "default",
        max_attempts: int = 5,
    ) -> JobState:
        with db_connection() as conn:
            with conn.cursor() as cur:
                job = create_job_with_cursor(
                    cur,
                    job_id=job_id or uuid4(),
                    job_type=job_type,
                    household_id=household_id,
                    document_id=document_id,
                    batch_id=batch_id,
                    payload=payload,
                    priority=priority,
                    queue_name=queue_name,
                    max_attempts=max_attempts,
                )
                fence_current_job(cur)
            conn.commit()
        return job

    def get_job(self, job_id: UUID, *, household_id: UUID | None = None) -> JobState | None:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM pipeline_jobs
                    WHERE id = %s
                      AND (%s::uuid IS NULL OR household_id = %s)
                    """,
                    (job_id, household_id, household_id),
                )
                row = cur.fetchone()
        return job_state_from_row(row) if row else None

    def list_jobs(
        self,
        *,
        household_id: UUID | None = None,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 100,
    ) -> list[JobState]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM pipeline_jobs
                    WHERE (%s::uuid IS NULL OR household_id = %s)
                      AND (%s::text IS NULL OR status = %s)
                      AND (%s::text IS NULL OR job_type = %s)
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (household_id, household_id, status, status, job_type, job_type, limit),
                )
                rows = cur.fetchall()
        return [job_state_from_row(row) for row in rows]

    def claim_next_job_record(
        self,
        *,
        worker_name: str,
        queue_name: str = "default",
        document_id: UUID | None = None,
        lease_seconds: int = 300,
    ) -> ClaimedJob | None:
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = claim_job(
                    cur,
                    worker_name=worker_name,
                    queue_name=queue_name,
                    document_id=document_id,
                    lease_seconds=lease_seconds,
                )
            conn.commit()
        return claimed_job_from_row(row) if row else None

    def heartbeat_job(
        self, *, job_id: UUID, claim_token: UUID, worker_name: str, lease_seconds: int = 300
    ) -> JobState:
        with db_connection(connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute("SET LOCAL lock_timeout = '2s'")
                row = renew_job(
                    cur,
                    attempt=JobAttempt(job_id, claim_token),
                    worker_name=worker_name,
                    lease_seconds=lease_seconds,
                )
            conn.commit()
        return job_state_from_row(row)

    def complete_job(
        self, *, job_id: UUID, claim_token: UUID, result: Mapping[str, Any] | None = None
    ) -> JobState:
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = complete_owned_job(
                    cur, attempt=JobAttempt(job_id, claim_token), result=result
                )
            conn.commit()
        return job_state_from_row(row)

    def fail_job(
        self,
        *,
        job_id: UUID,
        claim_token: UUID,
        error_class: str,
        message: str,
        retryable: bool = True,
        suppress: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> JobState:
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = fail_owned_job(
                    cur,
                    attempt=JobAttempt(job_id, claim_token),
                    error_class=error_class,
                    message=message,
                    retryable=retryable,
                    suppress=suppress,
                    details=details,
                )
            conn.commit()
        return job_state_from_row(row)

    def cancel_job(
        self,
        *,
        job_id: UUID,
        household_id: UUID | None = None,
        reason: str,
        include_running: bool = False,
        requested_by: str = "operator",
    ) -> JobState:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM pipeline_jobs
                    WHERE id = %s
                      AND (%s::uuid IS NULL OR household_id = %s)
                    FOR UPDATE
                    """,
                    (job_id, household_id, household_id),
                )
                current = cur.fetchone()
                if not current:
                    raise JobServiceError("Job not found.")
                row = _cancel_job_row(
                    cur,
                    current=current,
                    reason=reason,
                    include_running=include_running,
                    requested_by=requested_by,
                )
            conn.commit()
        return job_state_from_row(row)

    def cancel_jobs(
        self,
        *,
        household_id: UUID | None = None,
        reason: str,
        job_ids: Sequence[UUID] = (),
        document_ids: Sequence[UUID] = (),
        queue_names: Sequence[str] = (),
        statuses: Sequence[str] = ("queued", "failed"),
        title_prefix: str | None = None,
        include_running: bool = False,
        max_jobs: int = 250,
        requested_by: str = "operator",
    ) -> BulkCancelResult:
        if not job_ids and not document_ids and not title_prefix:
            raise JobServiceError(
                "Bulk job cancellation requires job_ids, document_ids, or title_prefix."
            )
        candidate_statuses = set(statuses or ("queued", "failed"))
        if include_running:
            candidate_statuses.update({"running", "leased"})
        elif candidate_statuses.intersection({"running", "leased"}):
            raise JobServiceError("Cancelling running jobs requires include_running=true.")
        unsupported = candidate_statuses - {"queued", "failed", "running", "leased"}
        if unsupported:
            unsupported_text = ", ".join(sorted(unsupported))
            raise JobServiceError(f"Unsupported cancellation statuses: {unsupported_text}.")

        with db_connection() as conn:
            with conn.cursor() as cur:
                candidate_ids = _candidate_cancel_job_ids(
                    cur,
                    household_id=household_id,
                    job_ids=job_ids,
                    document_ids=document_ids,
                    queue_names=queue_names,
                    statuses=tuple(sorted(candidate_statuses)),
                    title_prefix=title_prefix,
                    max_jobs=max_jobs,
                )
                cancelled: list[UUID] = []
                skipped: list[UUID] = []
                for candidate_id in candidate_ids:
                    cur.execute(
                        "SELECT * FROM pipeline_jobs WHERE id = %s FOR UPDATE",
                        (candidate_id,),
                    )
                    current = cur.fetchone()
                    if not current:
                        skipped.append(candidate_id)
                        continue
                    try:
                        _cancel_job_row(
                            cur,
                            current=current,
                            reason=reason,
                            include_running=include_running,
                            requested_by=requested_by,
                        )
                    except JobServiceError:
                        skipped.append(candidate_id)
                    else:
                        cancelled.append(candidate_id)
            conn.commit()
        return BulkCancelResult(
            cancelled_job_ids=tuple(cancelled),
            skipped_job_ids=tuple(skipped),
        )

    def retry_job(self, *, job_id: UUID, household_id: UUID | None = None) -> AcceptedJob:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pipeline_jobs
                    SET status = 'queued',
                        attempt_count = 0,
                        worker_name = NULL,
                        started_at = NULL,
                        lease_expires_at = NULL,
                        claim_token = NULL,
                        scheduled_at = now(),
                        finished_at = NULL,
                        error_json = '{}'::jsonb
                    WHERE id = %s
                      AND (
                        status IN ('failed', 'dead_letter', 'cancelled')
                        OR (
                          status = 'running'
                          AND lease_expires_at IS NOT NULL
                          AND lease_expires_at <= clock_timestamp()
                        )
                      )
                      AND (%s::uuid IS NULL OR household_id = %s)
                    RETURNING id, status::text
                    """,
                    (job_id, household_id, household_id),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise JobServiceError("Job is not retryable or does not exist.")
        return AcceptedJob.model_validate({"jobId": row["id"], "status": row["status"]})


def _cancel_job_row(
    cur: Any,
    *,
    current: Mapping[str, Any],
    reason: str,
    include_running: bool,
    requested_by: str,
) -> Mapping[str, Any]:
    status = str(current["status"])
    if status == "cancelled":
        return current
    if status in {"succeeded", "dead_letter"}:
        raise JobServiceError(f"Job in status '{status}' cannot be cancelled.")
    if status in {"running", "leased"} and not include_running:
        raise JobServiceError("Running job cancellation requires include_running=true.")
    if status not in {"queued", "failed", "running", "leased"}:
        raise JobServiceError(f"Job in status '{status}' cannot be cancelled.")
    # Cancellation metadata is a fresh event. Operator strings can contain source
    # text and are not safe diagnostics; prior failure codes must not survive.
    del reason, requested_by
    safe_error = safe_job_failure("JobCancelled", "")
    cur.execute(
        """
        UPDATE pipeline_jobs
        SET status = 'cancelled',
            finished_at = clock_timestamp(),
            lease_expires_at = NULL,
            claim_token = NULL,
            scheduled_at = clock_timestamp(),
            error_json = %s::jsonb || jsonb_build_object(
                'retryable', false,
                'cancelled_at', clock_timestamp()
            )
        WHERE id = %s
        RETURNING *
        """,
        (Jsonb(safe_error), current["id"]),
    )
    row = cur.fetchone()
    if not row:
        raise JobServiceError("Job cancellation failed.")
    return cast(Mapping[str, Any], row)


def _candidate_cancel_job_ids(
    cur: Any,
    *,
    household_id: UUID | None,
    job_ids: Sequence[UUID],
    document_ids: Sequence[UUID],
    queue_names: Sequence[str],
    statuses: Sequence[str],
    title_prefix: str | None,
    max_jobs: int,
) -> list[UUID]:
    job_id_filter = list(job_ids) if job_ids else None
    document_id_filter = list(document_ids) if document_ids else None
    queue_name_filter = [str(queue_name) for queue_name in queue_names] if queue_names else None
    title_filter = f"{title_prefix}%" if title_prefix else None
    params: list[Any] = [
        list(statuses),
        household_id,
        household_id,
        job_id_filter,
        job_id_filter,
        document_id_filter,
        document_id_filter,
        queue_name_filter,
        queue_name_filter,
        title_filter,
        title_filter,
        max_jobs,
    ]
    cur.execute(
        """
        SELECT j.id
        FROM pipeline_jobs j
        LEFT JOIN documents d ON d.id = j.document_id
        WHERE j.status::text = any(%s::text[])
          AND (%s::uuid IS NULL OR j.household_id = %s::uuid)
          AND (%s::uuid[] IS NULL OR j.id = any(%s::uuid[]))
          AND (%s::uuid[] IS NULL OR j.document_id = any(%s::uuid[]))
          AND (%s::text[] IS NULL OR j.queue_name = any(%s::text[]))
          AND (%s::text IS NULL OR d.title ILIKE %s)
        ORDER BY j.priority DESC, j.created_at ASC
        LIMIT %s
        """,
        params,
    )
    return [row["id"] for row in cur.fetchall()]


def record_service_health(
    *,
    service_name: str,
    status: str = "ok",
    metrics: Mapping[str, Any] | None = None,
) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO service_health_snapshots (service_name, status, metrics_json)
                VALUES (%s, %s, %s::jsonb)
                """,
                (service_name, status, Jsonb(dict(metrics or {}))),
            )
        conn.commit()
