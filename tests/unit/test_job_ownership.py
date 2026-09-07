from __future__ import annotations

from datetime import UTC, datetime
from threading import Event
from uuid import uuid4

import pytest

from lib.contracts import JobState
from lib.jobs import lease
from lib.jobs.errors import JobOwnershipLost
from lib.jobs.lease import keep_job_lease
from lib.jobs.models import ClaimedJob
from lib.jobs.ownership import JobAttempt, fence_current_job, job_attempt_scope


def claimed_job() -> ClaimedJob:
    return ClaimedJob(
        state=JobState(
            jobId=uuid4(), jobType="extract", status="running", createdAt=datetime.now(UTC)
        ),
        payload={},
        document_id=None,
        household_id=None,
        claim_token=uuid4(),
        lease_expires_at=datetime.now(UTC),
        attempt_count=1,
        max_attempts=5,
    )


class RecordingCursor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, query, args):
        self.calls.append((query, args))

    def fetchone(self):
        return {"id": uuid4()}


def test_request_scope_is_intentionally_unfenced_and_worker_scope_is_restored() -> None:
    cursor = RecordingCursor()
    fence_current_job(cursor)
    assert cursor.calls == []
    attempt = JobAttempt(uuid4(), uuid4())
    with job_attempt_scope(attempt, Event()):
        fence_current_job(cursor)
    assert cursor.calls[-1][1] == (attempt.job_id, attempt.claim_token)
    call_count = len(cursor.calls)
    fence_current_job(cursor)
    assert len(cursor.calls) == call_count


def test_lease_renews_while_synchronous_work_waits() -> None:
    renewed = Event()
    job = claimed_job()

    class Jobs:
        calls = []

        def heartbeat_job(self, **kwargs):
            self.calls.append(kwargs)
            renewed.set()
            return job.state

    jobs = Jobs()
    with keep_job_lease(jobs, job, worker_name="worker", lease_seconds=1, renewal_interval=0.01):
        assert renewed.wait(1), "Synchronous work prevented independent renewal"
        fence_current_job(RecordingCursor())
    assert jobs.calls[0]["claim_token"] == job.claim_token


def test_uncertain_renewal_refuses_publication_and_does_not_escape_worker(monkeypatch) -> None:
    renewed = Event()
    lost = Event()
    events = [Event(), lost]
    monkeypatch.setattr(lease, "Event", lambda: events.pop(0))

    class Jobs:
        def heartbeat_job(self, **kwargs):
            renewed.set()
            raise RuntimeError("database unavailable")

    reached_after_fence = False
    cursor = RecordingCursor()
    with keep_job_lease(
        Jobs(), claimed_job(), worker_name="worker", lease_seconds=1, renewal_interval=0.01
    ):
        assert renewed.wait(1)
        assert lost.wait(1)
        fence_current_job(cursor)
        reached_after_fence = True
    assert reached_after_fence is False


def test_known_ownership_loss_refuses_query_and_resets_context() -> None:
    lost = Event()
    lost.set()
    cursor = RecordingCursor()
    with job_attempt_scope(JobAttempt(uuid4(), uuid4()), lost):
        with pytest.raises(JobOwnershipLost):
            fence_current_job(cursor)
    fence_current_job(cursor)
    assert cursor.calls == []
