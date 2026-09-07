from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.jobs.errors import JobServiceError
from lib.jobs.lineage_repository import (
    descendants_are_running,
    load_job_lineage,
    lock_job_lineage,
    lock_root,
    require_current_ancestry,
    revoke_descendants,
)
from lib.jobs.models import BulkCancelResult
from lib.jobs.public_errors import safe_job_failure


def cancel_job(
    cur: Any,
    *,
    job_id: UUID,
    household_id: UUID | None,
    reason: str,
    include_running: bool,
    requested_by: str,
) -> Mapping[str, Any]:
    lock_job_lineage(cur, job_id)
    current = _locked_job(cur, job_id=job_id, household_id=household_id)
    if not include_running and descendants_are_running(cur, job_id):
        raise JobServiceError("Cancelling running descendants requires include_running=true.")
    result = cancel_job_row(
        cur,
        current=current,
        reason=reason,
        include_running=include_running,
        requested_by=requested_by,
    )
    revoke_descendants(cur, job_id)
    return result


def cancel_jobs(
    cur: Any,
    *,
    household_id: UUID | None,
    reason: str,
    job_ids: Sequence[UUID],
    document_ids: Sequence[UUID],
    queue_names: Sequence[str],
    statuses: Sequence[str],
    title_prefix: str | None,
    include_running: bool,
    max_jobs: int,
    requested_by: str,
) -> BulkCancelResult:
    if not job_ids and not document_ids and not title_prefix:
        raise JobServiceError(
            "Bulk job cancellation requires job_ids, document_ids, or title_prefix."
        )
    selected = set(statuses or ("queued", "failed"))
    if include_running:
        selected.update({"running", "leased"})
    elif selected.intersection({"running", "leased"}):
        raise JobServiceError("Cancelling running jobs requires include_running=true.")
    if selected - {"queued", "failed", "running", "leased", "succeeded"}:
        raise JobServiceError("Unsupported cancellation statuses.")
    ids = candidate_cancel_job_ids(
        cur,
        household_id=household_id,
        job_ids=job_ids,
        document_ids=document_ids,
        queue_names=queue_names,
        statuses=tuple(sorted(selected)),
        title_prefix=title_prefix,
        max_jobs=max_jobs,
    )
    # Bulk operations acquire every tree root in one order before any job row.
    roots = {load_job_lineage(cur, job_id)[0]["id"] for job_id in ids}
    for root_id in sorted(roots):
        lock_root(cur, root_id)
    cancelled = []
    skipped = []
    for job_id in ids:
        try:
            cancel_job(
                cur,
                job_id=job_id,
                household_id=household_id,
                reason=reason,
                include_running=include_running,
                requested_by=requested_by,
            )
        except JobServiceError:
            skipped.append(job_id)
        else:
            cancelled.append(job_id)
    return BulkCancelResult(tuple(cancelled), tuple(skipped))


def retry_job(cur: Any, *, job_id: UUID, household_id: UUID | None) -> Mapping[str, Any]:
    lineage = lock_job_lineage(cur, job_id)
    if lineage is None:
        raise JobServiceError("Job ancestry is unavailable.")
    require_current_ancestry(lineage)
    _locked_job(cur, job_id=job_id, household_id=household_id)
    cur.execute(
        """
        UPDATE pipeline_jobs
        SET status = 'queued', attempt_count = 0, worker_name = NULL, started_at = NULL,
            lease_expires_at = NULL, claim_token = NULL, scheduled_at = clock_timestamp(),
            finished_at = NULL, error_json = '{}'::jsonb, result_json = '{}'::jsonb
        WHERE id = %s AND lineage_revoked_at IS NULL
          AND (status IN ('failed', 'dead_letter', 'cancelled') OR
            (status = 'running' AND lease_expires_at <= clock_timestamp()))
        RETURNING id, status::text
        """,
        (job_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise JobServiceError("Job is not retryable or does not exist.")
    revoke_descendants(cur, job_id)
    return cast(Mapping[str, Any], row)


def _locked_job(cur: Any, *, job_id: UUID, household_id: UUID | None) -> Mapping[str, Any]:
    cur.execute(
        "SELECT * FROM pipeline_jobs WHERE id = %s "
        "AND (%s::uuid IS NULL OR household_id = %s) FOR UPDATE",
        (job_id, household_id, household_id),
    )
    row = cur.fetchone()
    if row is None:
        raise JobServiceError("Job not found.")
    return cast(Mapping[str, Any], row)


def cancel_job_row(
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
    if status == "succeeded":
        cur.execute(
            "SELECT 1 FROM pipeline_jobs WHERE parent_job_id = %s LIMIT 1", (current["id"],)
        )
        if cur.fetchone() is None:
            raise JobServiceError("A completed leaf job cannot be cancelled.")
        cur.execute(
            "UPDATE pipeline_jobs SET lineage_revoked_at = "
            "COALESCE(lineage_revoked_at, clock_timestamp()) WHERE id = %s RETURNING *",
            (current["id"],),
        )
        return cast(Mapping[str, Any], cur.fetchone())
    if status == "dead_letter":
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


def candidate_cancel_job_ids(
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
