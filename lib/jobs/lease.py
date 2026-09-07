from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Event, Thread
from typing import Protocol
from uuid import UUID

from lib.jobs.errors import JobOwnershipLost
from lib.jobs.models import ClaimedJob
from lib.jobs.ownership import JobAttempt, job_attempt_scope


class LeaseRenewer(Protocol):
    def heartbeat_job(
        self, *, job_id: UUID, claim_token: UUID, worker_name: str, lease_seconds: int
    ) -> object: ...


@contextmanager
def keep_job_lease(
    jobs: LeaseRenewer,
    claimed: ClaimedJob,
    *,
    worker_name: str,
    lease_seconds: int = 300,
    renewal_interval: float | None = None,
) -> Iterator[None]:
    """Renew independently of synchronous work and refuse writes after loss.

    SQL checks still fence every publication; renewal alone grants no right to
    commit. Renewal has bounded database timeouts. A stopped/unreachable thread
    cannot keep ownership alive indefinitely, and context cleanup is bounded.
    """
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    interval = renewal_interval if renewal_interval is not None else min(30.0, lease_seconds / 3)
    if not 0 < interval < lease_seconds:
        raise ValueError("renewal_interval must be positive and shorter than the lease")
    attempt = JobAttempt(claimed.state.job_id, claimed.claim_token)
    stop = Event()
    lost = Event()

    def renew() -> None:
        while not stop.wait(interval):
            try:
                renewed = jobs.heartbeat_job(
                    job_id=attempt.job_id,
                    claim_token=attempt.claim_token,
                    worker_name=worker_name,
                    lease_seconds=lease_seconds,
                )
                if renewed is None:
                    lost.set()
                    return
            except Exception:
                # Treat uncertainty as ownership loss; no private exception text
                # is logged and the DB lease expires normally if connectivity died.
                lost.set()
                return

    thread = Thread(target=renew, name="job-lease-renewal", daemon=True)
    with job_attempt_scope(attempt, lost):
        thread.start()
        try:
            yield
        except JobOwnershipLost:
            # Cancellation/reclaim is an expected losing-attempt outcome. Never
            # let the worker's failure handler mutate the newer owner's job.
            pass
        finally:
            stop.set()
            thread.join(timeout=1.0)
