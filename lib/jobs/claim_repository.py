from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID, uuid4

from lib.jobs.lineage_repository import lineage_allows_execution, lock_job_lineage


def claim_runnable_job(
    cur: Any,
    *,
    worker_name: str,
    queue_name: str,
    document_id: UUID | None,
    lease_seconds: int,
) -> Mapping[str, Any] | None:
    # No row lock before the root lock. A nonblocking root lock lets independent
    # trees progress while another tree publishes or is being cancelled.
    cur.execute(
        """
        SELECT j.id FROM pipeline_jobs j
        LEFT JOIN pipeline_jobs parent ON parent.id = j.parent_job_id
        WHERE j.status IN ('queued', 'failed') AND j.queue_name = %s
          AND (%s::uuid IS NULL OR j.document_id = %s)
          AND j.lineage_revoked_at IS NULL
          AND j.scheduled_at <= clock_timestamp() AND j.attempt_count < j.max_attempts
          AND (j.parent_job_id IS NULL OR (
            parent.status = 'succeeded' AND parent.lineage_revoked_at IS NULL
            AND j.parent_execution_generation = parent.execution_generation
          ))
        ORDER BY j.priority DESC, j.scheduled_at ASC, j.created_at ASC
        LIMIT 128
        """,
        (queue_name, document_id, document_id),
    )
    candidates = cur.fetchall()
    for candidate in candidates:
        lineage = lock_job_lineage(cur, candidate["id"], wait=False)
        if lineage is None or not lineage_allows_execution(lineage):
            continue
        cur.execute(
            "SELECT id FROM pipeline_jobs WHERE id = %s FOR UPDATE SKIP LOCKED",
            (candidate["id"],),
        )
        if cur.fetchone() is None:
            continue
        # State and wall clock are rechecked after both lock acquisitions.
        cur.execute(
            """
            UPDATE pipeline_jobs
            SET status = 'running', worker_name = %s, claim_token = %s,
                execution_generation = execution_generation + 1,
                lease_expires_at = clock_timestamp() + (%s * interval '1 second'),
                started_at = COALESCE(started_at, clock_timestamp()),
                attempt_count = attempt_count + 1
            WHERE id = %s AND status IN ('queued', 'failed')
              AND scheduled_at <= clock_timestamp() AND attempt_count < max_attempts
              AND lineage_revoked_at IS NULL
            RETURNING *
            """,
            (worker_name, uuid4(), lease_seconds, candidate["id"]),
        )
        row = cur.fetchone()
        if row is not None:
            return cast(Mapping[str, Any], row)
    return None
