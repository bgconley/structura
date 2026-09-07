"""Job ancestry authority, serialized independently of document/run authority.

Every lifecycle writer locks the immutable tree root before job rows. Claim and
recovery use nonblocking root locks. Bulk operators lock roots in UUID order.
These paths never acquire domain rows: existing publication transactions may
already hold domain locks before this lock, so reverse acquisition is forbidden.
Future document/run fencing must preserve or replace this ordering explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.jobs.errors import JobOwnershipLost, JobServiceError
from lib.jobs.public_errors import safe_job_failure


def load_job_lineage(cur: Any, job_id: UUID) -> list[Mapping[str, Any]]:
    cur.execute(
        """
        WITH RECURSIVE ancestors AS (
          SELECT id, parent_job_id, parent_execution_generation, execution_generation,
                 status, lineage_revoked_at, ARRAY[id] AS path, 0 AS depth
          FROM pipeline_jobs WHERE id = %s
          UNION ALL
          SELECT p.id, p.parent_job_id, p.parent_execution_generation, p.execution_generation,
                 p.status, p.lineage_revoked_at, a.path || p.id, a.depth + 1
          FROM pipeline_jobs p JOIN ancestors a ON p.id = a.parent_job_id
          WHERE NOT p.id = ANY(a.path) AND a.depth < 128
        ) SELECT * FROM ancestors ORDER BY depth DESC
        """,
        (job_id,),
    )
    rows = cast(list[Mapping[str, Any]], cur.fetchall())
    if not rows or rows[0]["parent_job_id"] is not None:
        raise JobServiceError("Job ancestry is missing or invalid.")
    return rows


def lock_root(cur: Any, root_id: UUID, *, wait: bool = True) -> bool:
    query = (
        "SELECT pg_advisory_xact_lock(hashtextextended(%s::text, 92231)) AS acquired"
        if wait
        else "SELECT pg_try_advisory_xact_lock(hashtextextended(%s::text, 92231)) AS acquired"
    )
    cur.execute(query, (root_id,))
    row = cur.fetchone()
    return wait or bool(row and row["acquired"])


def lock_job_lineage(
    cur: Any, job_id: UUID, *, wait: bool = True
) -> list[Mapping[str, Any]] | None:
    initial = load_job_lineage(cur, job_id)
    if not lock_root(cur, initial[0]["id"], wait=wait):
        return None
    # Parent links are immutable. Reread states after waiting for the root lock.
    return load_job_lineage(cur, job_id)


def lineage_allows_execution(rows: list[Mapping[str, Any]]) -> bool:
    if any(row["lineage_revoked_at"] is not None for row in rows):
        return False
    return all(
        parent["status"] == "succeeded"
        and child["parent_execution_generation"] == parent["execution_generation"]
        for parent, child in zip(rows, rows[1:], strict=False)
    )


def require_current_ancestry(rows: list[Mapping[str, Any]]) -> None:
    if not lineage_allows_execution(rows):
        raise JobOwnershipLost("Job ancestor was cancelled, replaced, or has not succeeded.")


def revoke_descendants(cur: Any, job_id: UUID) -> int:
    """Caller holds the tree-root lock; revoke every published descendant edge.

    Completed job records remain historical successes, but cannot authorize
    more work. Other descendants become cancelled and cannot be retried.
    """
    event = safe_job_failure("JobCancelled", "")
    event.pop("error_id")
    cur.execute(
        """
        WITH RECURSIVE descendants AS (
          SELECT id FROM pipeline_jobs WHERE parent_job_id = %s
          UNION ALL
          SELECT j.id FROM pipeline_jobs j JOIN descendants d ON j.parent_job_id = d.id
        ) UPDATE pipeline_jobs j
        SET lineage_revoked_at = COALESCE(lineage_revoked_at, clock_timestamp()),
            status = CASE WHEN status = 'succeeded' THEN status
                          ELSE 'cancelled'::job_status_enum END,
            claim_token = NULL, lease_expires_at = NULL,
            finished_at = COALESCE(finished_at, clock_timestamp()),
            error_json = CASE WHEN status = 'succeeded' THEN error_json ELSE
              %s::jsonb || jsonb_build_object('error_id', gen_random_uuid()::text,
                                             'retryable', false) END
        FROM descendants d WHERE j.id = d.id AND j.lineage_revoked_at IS NULL
        """,
        (job_id, Jsonb(event)),
    )
    return int(cur.rowcount)


def descendants_are_running(cur: Any, job_id: UUID) -> bool:
    """Caller holds the root lock, so this cancellation preflight stays valid."""
    cur.execute(
        """
        WITH RECURSIVE descendants AS (
          SELECT id, status FROM pipeline_jobs WHERE parent_job_id = %s
          UNION ALL
          SELECT j.id, j.status FROM pipeline_jobs j JOIN descendants d ON j.parent_job_id = d.id
        ) SELECT 1 FROM descendants WHERE status IN ('running', 'leased') LIMIT 1
        """,
        (job_id,),
    )
    return cur.fetchone() is not None
