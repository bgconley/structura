from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lib.config import get_settings
from lib.contracts import AcceptedJob, JobState
from lib.db.connection import db_connection

SENSITIVE_PAYLOAD_KEYS = {
    "document_text",
    "raw_document_text",
    "raw_text",
    "raw_model_output",
    "model_output",
    "prompt",
    "prompt_body",
    "sensitive_fields",
    "extracted_sensitive_fields",
}

SUPPORTED_QUEUE_TRANSPORTS = {"pgmq", "pipeline_jobs", "redis"}


@dataclass(frozen=True)
class QueueTransportProfile:
    requested: str
    active: str
    reason: str | None = None


@dataclass(frozen=True)
class ClaimedJob:
    state: JobState
    payload: dict[str, Any]
    document_id: UUID | None
    household_id: UUID | None


@dataclass(frozen=True)
class BulkCancelResult:
    cancelled_job_ids: tuple[UUID, ...]
    skipped_job_ids: tuple[UUID, ...]

    @property
    def cancelled_count(self) -> int:
        return len(self.cancelled_job_ids)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_job_ids)


class JobServiceError(Exception):
    pass


class PayloadSafetyError(JobServiceError):
    pass


def queue_transport_profile(requested: str | None = None) -> QueueTransportProfile:
    transport = (requested or get_settings().queue_transport).lower()
    if transport not in SUPPORTED_QUEUE_TRANSPORTS:
        supported = ", ".join(sorted(SUPPORTED_QUEUE_TRANSPORTS))
        raise JobServiceError(f"Unsupported queue transport '{transport}'. Supported: {supported}.")
    if transport == "pgmq":
        return QueueTransportProfile(
            requested=transport,
            active="pipeline_jobs",
            reason=(
                "PGMQ is the preferred transport, but Phase 0 uses the Postgres job "
                "ledger directly because the pinned ParadeDB PG17 image does not package PGMQ."
            ),
        )
    if transport == "redis":
        return QueueTransportProfile(
            requested=transport,
            active="pipeline_jobs",
            reason=(
                "Redis remains a fallback profile; Phase 0 keeps pipeline_jobs as durable truth."
            ),
        )
    return QueueTransportProfile(requested=transport, active="pipeline_jobs")


def retry_delay_seconds(
    attempt_count: int,
    *,
    base_seconds: int = 30,
    cap_seconds: int = 3600,
) -> int:
    exponent = max(attempt_count - 1, 0)
    return int(min(cap_seconds, base_seconds * (2**exponent)))


def sanitize_job_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    def walk(value: Any, path: tuple[str, ...]) -> Any:
        if isinstance(value, Mapping):
            sanitized: dict[str, Any] = {}
            for key, child in value.items():
                normalized = str(key).lower()
                if normalized in SENSITIVE_PAYLOAD_KEYS:
                    raise PayloadSafetyError(
                        f"Job payload key {'.'.join((*path, str(key)))} is not allowed."
                    )
                sanitized[str(key)] = walk(child, (*path, str(key)))
            return sanitized
        if isinstance(value, list):
            return [walk(item, path) for item in value]
        return value

    return cast(dict[str, Any], walk(dict(payload), ()))


def job_state_from_row(row: Mapping[str, Any]) -> JobState:
    error_json = row.get("error_json") or {}
    result_json = row.get("result_json") or {}
    return JobState.model_validate(
        {
            "jobId": row["id"],
            "jobType": row["job_type"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "startedAt": row.get("started_at"),
            "finishedAt": row.get("finished_at"),
            "errorMessage": error_json.get("message") or error_json.get("last_error"),
            "result": result_json,
        }
    )


def claimed_job_from_row(row: Mapping[str, Any]) -> ClaimedJob:
    payload = row.get("payload_json") or {}
    return ClaimedJob(
        state=job_state_from_row(row),
        payload=dict(payload) if isinstance(payload, Mapping) else {},
        document_id=cast(UUID | None, row.get("document_id")),
        household_id=cast(UUID | None, row.get("household_id")),
    )


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

    def claim_next_job(
        self,
        *,
        worker_name: str,
        queue_name: str = "default",
        document_id: UUID | None = None,
        lease_seconds: int = 300,
    ) -> JobState | None:
        claimed = self.claim_next_job_record(
            worker_name=worker_name,
            queue_name=queue_name,
            document_id=document_id,
            lease_seconds=lease_seconds,
        )
        return claimed.state if claimed else None

    def claim_next_job_record(
        self,
        *,
        worker_name: str,
        queue_name: str = "default",
        document_id: UUID | None = None,
        lease_seconds: int = 300,
    ) -> ClaimedJob | None:
        lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
        with db_connection() as conn:
            with conn.cursor() as cur:
                _recover_expired_running_jobs(
                    cur,
                    queue_name=queue_name,
                    document_id=document_id,
                )
                cur.execute(
                    """
                    WITH next_job AS (
                      SELECT id
                      FROM pipeline_jobs
                      WHERE status IN ('queued', 'failed')
                        AND queue_name = %s
                        AND (%s::uuid IS NULL OR document_id = %s)
                        AND scheduled_at <= now()
                        AND attempt_count < max_attempts
                      ORDER BY priority DESC, scheduled_at ASC, created_at ASC
                      FOR UPDATE SKIP LOCKED
                      LIMIT 1
                    )
                    UPDATE pipeline_jobs j
                    SET status = 'running',
                        worker_name = %s,
                        lease_expires_at = %s,
                        started_at = COALESCE(started_at, now()),
                        attempt_count = attempt_count + 1
                    FROM next_job
                    WHERE j.id = next_job.id
                    RETURNING j.*
                    """,
                    (queue_name, document_id, document_id, worker_name, lease_expires_at),
                )
                row = cur.fetchone()
            conn.commit()
        return claimed_job_from_row(row) if row else None

    def heartbeat_job(
        self,
        *,
        job_id: UUID,
        worker_name: str,
        lease_seconds: int = 300,
    ) -> JobState | None:
        lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE pipeline_jobs
                    SET worker_name = %s,
                        lease_expires_at = %s
                    WHERE id = %s
                      AND status = 'running'
                    RETURNING *
                    """,
                    (worker_name, lease_expires_at, job_id),
                )
                row = cur.fetchone()
            conn.commit()
        return job_state_from_row(row) if row else None

    def complete_job(self, *, job_id: UUID, result: Mapping[str, Any] | None = None) -> JobState:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM pipeline_jobs WHERE id = %s FOR UPDATE", (job_id,))
                current = cur.fetchone()
                if not current:
                    raise JobServiceError("Job not found.")
                if current["status"] == "cancelled":
                    return job_state_from_row(current)
                cur.execute(
                    """
                    UPDATE pipeline_jobs
                    SET status = 'succeeded',
                        finished_at = now(),
                        lease_expires_at = NULL,
                        result_json = %s::jsonb
                    WHERE id = %s
                    RETURNING *
                    """,
                    (Jsonb(dict(result or {})), job_id),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise JobServiceError("Job update failed.")
        return job_state_from_row(row)

    def fail_job(
        self,
        *,
        job_id: UUID,
        error_class: str,
        message: str,
        retryable: bool = True,
        suppress: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> JobState:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM pipeline_jobs WHERE id = %s FOR UPDATE", (job_id,))
                current = cur.fetchone()
                if not current:
                    raise JobServiceError("Job not found.")
                if current["status"] == "cancelled":
                    return job_state_from_row(current)
                status = "failed"
                if current["attempt_count"] >= current["max_attempts"] or not retryable:
                    status = "dead_letter"
                retry_after_seconds = retry_delay_seconds(current["attempt_count"])
                next_retry_at = datetime.now(UTC) + timedelta(seconds=retry_after_seconds)
                error_json = {
                    "document_id": str(current["document_id"]) if current["document_id"] else None,
                    "stage": current["job_type"],
                    "error_class": error_class,
                    "message": message,
                    "last_error": message,
                    "retryable": retryable,
                    "retry_action": f"/api/v1/admin/jobs/{job_id}/retry",
                    "retry_after_seconds": retry_after_seconds if status == "failed" else None,
                    "next_retry_at": next_retry_at.isoformat() if status == "failed" else None,
                    "dismissed_at": None,
                    "suppressed": suppress,
                }
                if details:
                    error_json["details"] = dict(details)
                cur.execute(
                    """
                    UPDATE pipeline_jobs
                    SET status = %s,
                        finished_at = CASE WHEN %s = 'dead_letter' THEN now() ELSE finished_at END,
                        lease_expires_at = NULL,
                        scheduled_at = CASE WHEN %s = 'failed' THEN %s ELSE scheduled_at END,
                        error_json = %s::jsonb
                    WHERE id = %s
                    RETURNING *
                    """,
                    (status, status, status, next_retry_at, Jsonb(error_json), job_id),
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            raise JobServiceError("Job update failed.")
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
                        scheduled_at = now(),
                        finished_at = NULL,
                        error_json = '{}'::jsonb
                    WHERE id = %s
                      AND (
                        status IN ('failed', 'dead_letter', 'cancelled')
                        OR (
                          status = 'running'
                          AND lease_expires_at IS NOT NULL
                          AND lease_expires_at <= now()
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


def _recover_expired_running_jobs(
    cur: Any,
    *,
    queue_name: str,
    document_id: UUID | None,
) -> int:
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
            scheduled_at = CASE
              WHEN attempt_count >= max_attempts THEN scheduled_at
              ELSE now()
            END,
            finished_at = CASE
              WHEN attempt_count >= max_attempts THEN now()
              ELSE finished_at
            END,
            error_json = jsonb_strip_nulls(
              COALESCE(error_json, '{}'::jsonb)
              || jsonb_build_object(
                'error_class',
                'WorkerLeaseExpired',
                'message',
                'Worker lease expired before completion.',
                'last_error',
                'Worker lease expired before completion.',
                'retryable',
                attempt_count < max_attempts,
                'retry_action',
                CASE
                  WHEN attempt_count >= max_attempts THEN '/api/v1/admin/jobs/' || id || '/retry'
                  ELSE NULL
                END
              )
            )
        WHERE status = 'running'
          AND queue_name = %s
          AND (%s::uuid IS NULL OR document_id = %s)
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at <= now()
        """,
        (queue_name, document_id, document_id),
    )
    return int(cur.rowcount)


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
    cur.execute(
        """
        UPDATE pipeline_jobs
        SET status = 'cancelled',
            finished_at = now(),
            lease_expires_at = NULL,
            scheduled_at = now(),
            error_json = jsonb_strip_nulls(
              COALESCE(error_json, '{}'::jsonb)
              || jsonb_build_object(
                'error_class', 'JobCancelled',
                'message', %s::text,
                'last_error', %s::text,
                'retryable', false,
                'cancelled_by', %s::text,
                'cancelled_at', now()
              )
            )
        WHERE id = %s
        RETURNING *
        """,
        (reason, reason, requested_by, current["id"]),
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
    clauses = ["j.status::text = any(%s)"]
    params: list[Any] = [list(statuses)]
    if household_id is not None:
        clauses.append("j.household_id = %s")
        params.append(household_id)
    if job_ids:
        clauses.append("j.id = any(%s)")
        params.append(list(job_ids))
    if document_ids:
        clauses.append("j.document_id = any(%s)")
        params.append(list(document_ids))
    if queue_names:
        clauses.append("j.queue_name = any(%s)")
        params.append([str(queue_name) for queue_name in queue_names])
    if title_prefix:
        clauses.append("d.title ILIKE %s")
        params.append(f"{title_prefix}%")
    params.append(max_jobs)
    cur.execute(
        f"""
        SELECT j.id
        FROM pipeline_jobs j
        LEFT JOIN documents d ON d.id = j.document_id
        WHERE {" AND ".join(clauses)}
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
