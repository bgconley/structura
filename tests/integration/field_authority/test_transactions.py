from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from queue import Queue
from threading import Event

import pytest
from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.fact_authority import projection_repository
from lib.review import canonical_field_repository as fields
from lib.review import canonical_read_repository as reads
from lib.review.errors import ReviewRepositoryError

from ..test_completion_authorization import observe_lock_backend, wait_until_blocked
from .support import candidate, confirm, envelope, reject, seed_chunk, snapshot


@pytest.mark.parametrize("failure_phase", ["projection", "enqueue"])
def test_projection_or_enqueue_failure_rolls_back_entire_human_decision(
    promotion_document, monkeypatch, failure_phase
):
    document_id, access = promotion_document
    item = candidate(document_id, "Rollback the entire decision")
    seed_chunk(document_id)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO review_tasks(document_id,task_type,status,metadata_json) "
            "VALUES (%s,'field_review','open',%s)",
            (document_id, Jsonb({"fieldPath": item["field_path"], "candidateId": str(item["id"])})),
        )
    before = snapshot(document_id)
    name = (
        "refresh_accepted_projection"
        if failure_phase == "projection"
        else "enqueue_embed_document_job"
    )
    original = getattr(projection_repository, name)

    def completed_phase_then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected failure after persistence")

    monkeypatch.setattr(projection_repository, name, completed_phase_then_fail)
    with pytest.raises(RuntimeError, match="Injected failure"):
        confirm(document_id, access, item)
    assert snapshot(document_id) == before


@pytest.mark.parametrize("revocation", ["disabled_actor", "removed_membership"])
def test_review_rechecks_revocation_after_real_privilege_lock_wait(
    promotion_document, monkeypatch, revocation
):
    document_id, access = promotion_document
    item = candidate(document_id, "Revocation wins before review")
    before = snapshot(document_id)
    backends = observe_lock_backend(monkeypatch, fields, "assert_writable")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            if revocation == "disabled_actor":
                cur.execute("UPDATE users SET is_disabled=true WHERE id=%s", (access.user_id,))
            else:
                cur.execute(
                    "DELETE FROM household_memberships WHERE user_id=%s AND household_id=%s",
                    (access.user_id, access.household_id),
                )
            waiting = pool.submit(confirm, document_id, access, item)
            try:
                wait_until_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            with pytest.raises(ReviewRepositoryError, match="Document not found"):
                waiting.result(timeout=5)
    assert snapshot(document_id) == before


def pause_after_projection(monkeypatch):
    completed, release = Queue(), Event()
    original = fields.refresh_projection_and_enqueue

    def paused(cur, **kwargs):
        result = original(cur, **kwargs)
        completed.put(cur.connection.info.backend_pid)
        if not release.wait(timeout=10):
            raise AssertionError("Test did not release the review transaction")
        return result

    monkeypatch.setattr(fields, "refresh_projection_and_enqueue", paused)
    return completed, release


def test_actor_fk_and_job_enqueue_do_not_invert_review_authority_locks(
    promotion_document, monkeypatch
):
    document_id, access = promotion_document
    item = candidate(document_id, "Review committed before disable")
    # Pause just before projection/enqueue, while the actor and document locks
    # are held. The concurrent actor writer must wait; review can still enqueue.
    ready, disabled = Queue(), Queue()
    release = Event()
    original = fields.refresh_projection_and_enqueue

    def paused_before_enqueue(cur, **kwargs):
        ready.put(cur.connection.info.backend_pid)
        if not release.wait(timeout=10):
            raise AssertionError("Test did not release the enqueue transaction")
        return original(cur, **kwargs)

    def disable_actor():
        with db_connection() as conn, conn.cursor() as cur:
            disabled.put(conn.info.backend_pid)
            cur.execute("UPDATE users SET is_disabled=true WHERE id=%s", (access.user_id,))

    monkeypatch.setattr(fields, "refresh_projection_and_enqueue", paused_before_enqueue)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reviewing = pool.submit(confirm, document_id, access, item)
        review_pid = ready.get(timeout=5)
        disabling = pool.submit(disable_actor)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                wait_until_blocked(cur, review_pid, disabled.get(timeout=5))
        finally:
            release.set()
        assert reviewing.result(timeout=5).decision.disposition == "confirmed"
        disabling.result(timeout=5)
    current = snapshot(document_id)
    assert len(current["decisions"]) == len(current["events"]) == len(current["jobs"]) == 1
    assert current["projection"]["state"] == "current"


def test_reader_waits_for_whole_decision_projection_and_returns_coherent_snapshot(
    promotion_document, monkeypatch
):
    document_id, access = promotion_document
    candidate(document_id, "No canonical row required")
    completed, release = pause_after_projection(monkeypatch)
    read_backend = Queue()

    @contextmanager
    def observed_read_connection():
        with db_connection() as conn:
            read_backend.put(conn.info.backend_pid)
            yield conn

    monkeypatch.setattr(reads, "db_connection", observed_read_connection)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rejecting = pool.submit(reject, document_id, access, "invoice.purchase_order")
        writer_pid = completed.get(timeout=5)
        reading = pool.submit(envelope, document_id, access)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                wait_until_blocked(cur, writer_pid, read_backend.get(timeout=5))
        finally:
            release.set()
        result = rejecting.result(timeout=5)
        read = reading.result(timeout=5)
    assert read.items == [] and read.decisions == [result.decision]
    assert read.projection == result.projection
    assert read.projection.state == "current"
