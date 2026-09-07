from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Event
from typing import Any
from uuid import UUID

from lib.jobs.errors import JobOwnershipLost


@dataclass(frozen=True)
class JobAttempt:
    job_id: UUID
    claim_token: UUID


@dataclass(frozen=True)
class AttemptScope:
    attempt: JobAttempt
    lost: Event


_CURRENT_ATTEMPT: ContextVar[AttemptScope | None] = ContextVar("job_attempt", default=None)


@contextmanager
def job_attempt_scope(attempt: JobAttempt, lost: Event) -> Iterator[None]:
    token = _CURRENT_ATTEMPT.set(AttemptScope(attempt, lost))
    try:
        yield
    finally:
        _CURRENT_ATTEMPT.reset(token)


def require_owned_job(cur: Any, attempt: JobAttempt) -> None:
    """Lock and fence the attempt inside the caller's publication transaction.

    Call after external work, before commit. The row lock serializes ownership
    revocation/reclaim with publication. Use the DB wall clock, not transaction
    start time; model calls may have taken longer than a lease.
    """
    cur.execute(
        """
        SELECT id FROM pipeline_jobs WHERE id = %s
        FOR UPDATE
        """,
        (attempt.job_id,),
    )
    if cur.fetchone() is None:
        raise JobOwnershipLost("Job attempt no longer owns a live lease.")
    # Re-evaluate time after acquiring the lock; waiting for a transaction that
    # leaves this row unchanged must not admit a lease that expired meanwhile.
    cur.execute(
        """
        SELECT id FROM pipeline_jobs
        WHERE id = %s AND claim_token = %s AND status = 'running'
          AND lease_expires_at > clock_timestamp()
        """,
        (attempt.job_id, attempt.claim_token),
    )
    if cur.fetchone() is None:
        raise JobOwnershipLost("Job attempt no longer owns a live lease.")


def fence_current_job(cur: Any) -> None:
    """Fence an explicitly worker-scoped commit; ordinary API transactions opt out.

    Request-side services also use these repositories without an execution
    lease. They retain their own authorization/transaction rules. Every real
    worker must establish job_attempt_scope before invoking domain services.
    """
    scope = _CURRENT_ATTEMPT.get()
    if scope is None:
        return
    if scope.lost.is_set():
        raise JobOwnershipLost("Job attempt renewal stopped; publication is refused.")
    require_owned_job(cur, scope.attempt)
