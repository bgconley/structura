from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lib.contracts import AcceptedJob, JobState
from lib.db.connection import db_connection
from lib.jobs import operator_repository as operators
from lib.jobs.creation_repository import insert_job
from lib.jobs.errors import JobServiceError as JobServiceError
from lib.jobs.errors import PayloadSafetyError as PayloadSafetyError
from lib.jobs.lifecycle_repository import (
    claim_job,
    complete_owned_job,
    fail_owned_job,
    renew_job,
)
from lib.jobs.models import BulkCancelResult, ClaimedJob
from lib.jobs.models import QueueTransportProfile as QueueTransportProfile
from lib.jobs.ownership import (
    JobAttempt,
    fence_current_job,
)
from lib.jobs.payload_policy import queue_transport_profile
from lib.jobs.payload_policy import retry_delay_seconds as retry_delay_seconds
from lib.jobs.payload_policy import sanitize_job_payload as sanitize_job_payload
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
    processing_run_id: UUID | None = None,
    parse_generation_id: UUID | None = None,
) -> JobState:
    row = insert_job(
        cur,
        job_id=job_id,
        job_type=job_type,
        household_id=household_id,
        document_id=document_id,
        batch_id=batch_id,
        payload=payload,
        priority=priority,
        queue_name=queue_name,
        max_attempts=max_attempts,
        processing_run_id=processing_run_id,
        parse_generation_id=parse_generation_id,
    )
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
        processing_run_id: UUID | None = None,
        parse_generation_id: UUID | None = None,
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
                    processing_run_id=processing_run_id,
                    parse_generation_id=parse_generation_id,
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
                row = operators.cancel_job(
                    cur,
                    job_id=job_id,
                    household_id=household_id,
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
        with db_connection() as conn:
            with conn.cursor() as cur:
                result = operators.cancel_jobs(
                    cur,
                    household_id=household_id,
                    reason=reason,
                    job_ids=job_ids,
                    document_ids=document_ids,
                    queue_names=queue_names,
                    statuses=statuses,
                    title_prefix=title_prefix,
                    include_running=include_running,
                    max_jobs=max_jobs,
                    requested_by=requested_by,
                )
            conn.commit()
        return result

    def retry_job(self, *, job_id: UUID, household_id: UUID | None = None) -> AcceptedJob:
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = operators.retry_job(cur, job_id=job_id, household_id=household_id)
            conn.commit()
        return AcceptedJob.model_validate({"jobId": row["id"], "status": row["status"]})


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
