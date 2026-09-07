from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from uuid import uuid4

import pytest

from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.documents.canonical_parse import mark_parse_failed
from lib.jobs import JobOwnershipLost, JobService, JobServiceError, create_job_with_cursor
from lib.jobs.lifecycle_repository import renew_job
from lib.jobs.operator_repository import cancel_job
from lib.jobs.ownership import JobAttempt, fence_current_job, job_attempt_scope
from lib.jobs.recovery_repository import recover_expired_running_jobs

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Requires an isolated database migrated through 092.",
)


@pytest.fixture
def queue(monkeypatch):
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    yield f"lineage-{uuid4()}"
    get_settings.cache_clear()


def _parent(queue, *, lease_seconds=300, household_id=None, document_id=None):
    jobs = JobService()
    jobs.create_job(
        job_type="extract", queue_name=queue, household_id=household_id, document_id=document_id
    )
    parent = jobs.claim_next_job_record(
        worker_name="parent", queue_name=queue, lease_seconds=lease_seconds
    )
    assert parent
    return jobs, parent


def _child(jobs, parent, queue):
    with job_attempt_scope(JobAttempt(parent.state.job_id, parent.claim_token), Event()):
        return jobs.create_job(job_type="extract", queue_name=queue)


def _complete(jobs, claimed):
    return jobs.complete_job(job_id=claimed.state.job_id, claim_token=claimed.claim_token)


def _row(job_id):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM pipeline_jobs WHERE id = %s", (job_id,))
        return cur.fetchone()


def test_children_capture_parent_attempt_and_wait_for_parent_success(queue):
    jobs, parent = _parent(queue)
    child = _child(jobs, parent, queue)
    row = _row(child.job_id)
    assert row["parent_job_id"] == parent.state.job_id
    assert row["parent_execution_generation"] == _row(parent.state.job_id)["execution_generation"]
    assert jobs.claim_next_job_record(worker_name="child", queue_name=queue) is None
    _complete(jobs, parent)
    claimed = jobs.claim_next_job_record(worker_name="child", queue_name=queue)
    assert claimed and claimed.state.job_id == child.job_id
    _complete(jobs, claimed)


def test_successful_parent_cancellation_revokes_active_subtree_and_preserves_history(queue):
    jobs, parent = _parent(queue)
    child = _child(jobs, parent, queue)
    _complete(jobs, parent)
    claimed_child = jobs.claim_next_job_record(worker_name="child", queue_name=queue)
    assert claimed_child
    grandchild = _child(jobs, claimed_child, queue)
    with pytest.raises(JobServiceError):
        jobs.cancel_job(job_id=parent.state.job_id, reason="Needs running opt in")
    result = jobs.cancel_job(
        job_id=parent.state.job_id, reason="Cancel downstream work", include_running=True
    )
    assert result.status == "succeeded"
    assert result.lineage_revoked_at is not None
    assert result.model_dump(by_alias=True)["lineageRevokedAt"] is not None
    for state in (child, grandchild):
        current = jobs.get_job(state.job_id)
        assert current.status == "cancelled" and current.lineage_revoked_at is not None
        with pytest.raises(JobServiceError):
            jobs.retry_job(job_id=state.job_id)
    with pytest.raises(JobOwnershipLost):
        _complete(jobs, claimed_child)
    with pytest.raises(JobOwnershipLost):
        _child(jobs, claimed_child, queue)
    assert jobs.claim_next_job_record(worker_name="late", queue_name=queue) is None


def test_retry_never_resurrects_old_descendants_or_reuses_parent_generation(queue):
    jobs, first = _parent(queue)
    old_child = _child(jobs, first, queue)
    first_generation = _row(first.state.job_id)["execution_generation"]
    jobs.cancel_job(job_id=first.state.job_id, reason="Retry root", include_running=True)
    jobs.retry_job(job_id=first.state.job_id)
    second = jobs.claim_next_job_record(worker_name="second", queue_name=queue)
    assert second and second.state.job_id == first.state.job_id
    assert _row(second.state.job_id)["execution_generation"] > first_generation
    with pytest.raises(JobServiceError):
        jobs.retry_job(job_id=old_child.job_id)
    with pytest.raises(JobOwnershipLost):
        _child(jobs, first, queue)
    fresh_child = _child(jobs, second, queue)
    _complete(jobs, second)
    claimed = jobs.claim_next_job_record(worker_name="fresh", queue_name=queue)
    assert claimed and claimed.state.job_id == fresh_child.job_id


def test_valid_child_lease_cannot_publish_after_parent_generation_changes(queue):
    jobs, parent = _parent(queue)
    child = _child(jobs, parent, queue)
    _complete(jobs, parent)
    claimed = jobs.claim_next_job_record(worker_name="child", queue_name=queue)
    assert claimed and claimed.state.job_id == child.job_id
    # Isolate the ancestry fence from token/status revocation: the child retains
    # a running status and its valid unexpired token throughout this test.
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_jobs SET execution_generation = execution_generation + 1 "
            "WHERE id = %s",
            (parent.state.job_id,),
        )
    owner = AuthService().bootstrap_admin(
        email=f"lineage-{uuid4()}@example.com", password="minimum8", household_name="Lineage"
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents (title, ingestion_source, household_id, owner_user_id) "
            "VALUES ('Lineage source','web_upload',%s,%s) RETURNING id",
            (owner.household_id, owner.user_id),
        )
        document_id = cur.fetchone()["id"]
    with (
        pytest.raises(JobOwnershipLost),
        job_attempt_scope(JobAttempt(claimed.state.job_id, claimed.claim_token), Event()),
    ):
        mark_parse_failed(
            document_id=document_id,
            error_class="RuntimeError",
            message="Stale",
            job_id=claimed.state.job_id,
        )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT metadata_json FROM documents WHERE id = %s", (document_id,))
        assert "phase3" not in cur.fetchone()["metadata_json"]
    row = _row(child.job_id)
    assert row["status"] == "running" and row["claim_token"] == claimed.claim_token


def _wait_for_lock(pid):
    deadline = time.monotonic() + 5
    with db_connection() as conn, conn.cursor() as cur:
        while time.monotonic() < deadline:
            cur.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pid,))
            row = cur.fetchone()
            if row and row["wait_event_type"] == "Lock":
                return
            time.sleep(0.01)
    pytest.fail("Competing connection never reached the expected lineage lock")


def test_cancel_waits_for_concurrent_enqueue_and_revokes_the_new_child(queue):
    jobs, parent = _parent(queue)
    pids = Queue()

    def cancel_in_another_connection():
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_backend_pid() AS pid")
            pids.put(cur.fetchone()["pid"])
            return cancel_job(
                cur,
                job_id=parent.state.job_id,
                household_id=None,
                reason="Cancel",
                requested_by="test",
                include_running=True,
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with (
            job_attempt_scope(JobAttempt(parent.state.job_id, parent.claim_token), Event()),
            db_connection() as conn,
            conn.cursor() as cur,
        ):
            child = create_job_with_cursor(
                cur, job_id=uuid4(), job_type="extract", queue_name=queue
            )
            future = pool.submit(cancel_in_another_connection)
            _wait_for_lock(pids.get(timeout=5))
            assert not future.done()
            conn.commit()
        assert future.result(timeout=5)["status"] == "cancelled"
    assert jobs.get_job(child.job_id).lineage_revoked_at is not None
    assert jobs.get_job(child.job_id).status == "cancelled"


def test_enqueue_waits_for_cancellation_then_fails_without_creating_child(queue):
    _jobs, parent = _parent(queue)
    pids = Queue()
    child_id = uuid4()

    def enqueue_in_another_connection():
        with (
            job_attempt_scope(JobAttempt(parent.state.job_id, parent.claim_token), Event()),
            db_connection() as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT pg_backend_pid() AS pid")
            pids.put(cur.fetchone()["pid"])
            return create_job_with_cursor(
                cur, job_id=child_id, job_type="extract", queue_name=queue
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_connection() as conn, conn.cursor() as cur:
            cancel_job(
                cur,
                job_id=parent.state.job_id,
                household_id=None,
                reason="Cancel",
                requested_by="test",
                include_running=True,
            )
            future = pool.submit(enqueue_in_another_connection)
            _wait_for_lock(pids.get(timeout=5))
            conn.commit()
        with pytest.raises(JobOwnershipLost):
            future.result(timeout=5)
    assert _row(child_id) is None


def test_recovery_skips_locked_renewal_and_rechecks_committed_lease(queue):
    _jobs, parent = _parent(queue, lease_seconds=1)
    with db_connection() as conn, conn.cursor() as cur:
        renew_job(
            cur,
            attempt=JobAttempt(parent.state.job_id, parent.claim_token),
            worker_name="parent",
            lease_seconds=30,
        )
        # A concurrent recovery sees the old expired version while renewal is
        # uncommitted. It must skip the locked tree instead of stealing the job.
        cur.execute("SELECT pg_sleep(1.1)")
        with db_connection() as other, other.cursor() as other_cur:
            assert recover_expired_running_jobs(other_cur, queue_name=queue, document_id=None) == 0
        conn.commit()
    with db_connection() as conn, conn.cursor() as cur:
        assert recover_expired_running_jobs(cur, queue_name=queue, document_id=None) == 0
    assert _row(parent.state.job_id)["claim_token"] == parent.claim_token


def test_expired_parent_recovery_revokes_children_before_a_new_attempt(queue):
    jobs, parent = _parent(queue)
    child = _child(jobs, parent, queue)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_jobs SET lease_expires_at = "
            "clock_timestamp() - interval '1 second' "
            "WHERE id = %s",
            (parent.state.job_id,),
        )
    second = jobs.claim_next_job_record(worker_name="replacement", queue_name=queue)
    assert second and second.state.job_id == parent.state.job_id
    assert jobs.get_job(child.job_id).lineage_revoked_at is not None
    with pytest.raises(JobServiceError):
        jobs.retry_job(job_id=child.job_id)


def test_sibling_publication_and_child_fk_locks_do_not_invert_root_order(queue):
    owner = AuthService().bootstrap_admin(
        email=f"lineage-lock-{uuid4()}@example.com",
        password="minimum8",
        household_name="Lineage lock",
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents (title, ingestion_source, household_id, owner_user_id) "
            "VALUES ('Lock source','web_upload',%s,%s) RETURNING id",
            (owner.household_id, owner.user_id),
        )
        document_id = cur.fetchone()["id"]
    jobs, parent = _parent(queue, household_id=owner.household_id, document_id=document_id)
    _child(jobs, parent, queue)
    _child(jobs, parent, queue)
    _complete(jobs, parent)
    first = jobs.claim_next_job_record(worker_name="first", queue_name=queue)
    second = jobs.claim_next_job_record(worker_name="second", queue_name=queue)
    assert first and second
    pids = Queue()

    def enqueue_sibling_child():
        with (
            job_attempt_scope(JobAttempt(second.state.job_id, second.claim_token), Event()),
            db_connection() as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT pg_backend_pid() AS pid")
            pids.put(cur.fetchone()["pid"])
            return create_job_with_cursor(cur, job_id=uuid4(), job_type="extract", queue_name=queue)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with (
            job_attempt_scope(JobAttempt(first.state.job_id, first.claim_token), Event()),
            db_connection() as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SET LOCAL lock_timeout = '3s'")
            cur.execute("SELECT id FROM documents WHERE id = %s FOR UPDATE", (document_id,))
            future = pool.submit(enqueue_sibling_child)
            _wait_for_lock(pids.get(timeout=5))
            # Enqueue must be waiting on the document without holding the root.
            # The former root-first FK INSERT would deadlock at this fence.
            fence_current_job(cur)
            conn.commit()
        child = future.result(timeout=5)
    row = _row(child.job_id)
    assert row["parent_job_id"] == second.state.job_id
    assert row["document_id"] == document_id


def test_worker_child_cannot_change_scope_after_first_enqueue(queue):
    jobs, parent = _parent(queue)
    with (
        job_attempt_scope(JobAttempt(parent.state.job_id, parent.claim_token), Event()),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        first = create_job_with_cursor(cur, job_id=uuid4(), job_type="extract", queue_name=queue)
        with pytest.raises(JobServiceError, match="retain parent"):
            create_job_with_cursor(
                cur, job_id=uuid4(), job_type="extract", queue_name=queue, document_id=uuid4()
            )
        conn.commit()
    assert _row(first.job_id)["parent_job_id"] == parent.state.job_id
