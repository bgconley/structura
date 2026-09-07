from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from uuid import uuid4

import pytest

from lib.auth.credential_repository import bootstrap_admin
from lib.auth.primitives import hash_password
from lib.db.connection import db_connection
from lib.document_processing import checkpoint_repository, run_repository
from lib.document_processing.authority_repository import fence_processing_attempt
from lib.document_processing.errors import ProcessingAuthorityLost, ProcessingError
from lib.document_processing.service import DocumentProcessingService
from lib.jobs import create_job_with_cursor

from .authority_cases import make_granted_member, revoke, token_request


def wait_for_blocked(cur, blocker, waiter):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        cur.execute("SELECT pg_blocking_pids(%s) AS blockers", (waiter,))
        if blocker in cur.fetchone()["blockers"]:
            return
        time.sleep(0.01)
    raise AssertionError("The independent connection did not wait for the authority holder")


def start_with_cursor(cur, processing):
    return run_repository.start_parse_run(
        cur,
        document_id=processing.document_id,
        principal=processing.principal,
        original_asset_id=processing.asset_id,
        original_sha256=processing.original_sha256,
        request_key=uuid4(),
        configuration=processing.configuration,
        queue_name=processing.queue,
    )


@pytest.mark.parametrize(
    "change",
    [
        "disabled",
        "membership_removed",
        "viewer",
        "private_document",
        "refiled",
        "grant_removed",
        "token_revoked",
        "token_read_only",
    ],
)
def test_revocation_committing_while_checkpoint_waits_wins(processing, change):
    request = token_request(processing) if change.startswith("token_") else processing
    _, grant_id = make_granted_member(request)
    run, service = request.start(), DocumentProcessingService()
    claimed = request.claim()
    with request.scope(claimed):
        service.initialize_inventory(run.binding, request.inventory)
    pids = Queue()

    def publish():
        with request.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            checkpoint_repository.persist_checkpoint(cur, run.binding, request.checkpoint(run))
            fence_processing_attempt(cur, run.binding)
            conn.commit()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_connection() as conn, conn.cursor() as cur:
            revoke(cur, request, change, grant_id=grant_id)
            future = pool.submit(publish)
            try:
                wait_for_blocked(cur, conn.info.backend_pid, pids.get(timeout=5))
            finally:
                conn.commit()
        with pytest.raises(ProcessingAuthorityLost):
            future.result(timeout=10)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id=%s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 0


@pytest.mark.parametrize("change", ["disabled", "grant_removed", "token_revoked"])
def test_publication_holds_authority_until_commit_then_revocation_blocks_next_write(
    processing, change
):
    request = token_request(processing) if change.startswith("token_") else processing
    _, grant_id = make_granted_member(request)
    run, service = request.start(), DocumentProcessingService()
    claimed = request.claim()
    with request.scope(claimed):
        service.initialize_inventory(run.binding, request.inventory)
    pids = Queue()

    def revoke_authority():
        with db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            revoke(cur, request, change, grant_id=grant_id)
            conn.commit()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with request.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            checkpoint_repository.persist_checkpoint(cur, run.binding, request.checkpoint(run))
            future = pool.submit(revoke_authority)
            try:
                wait_for_blocked(cur, conn.info.backend_pid, pids.get(timeout=5))
                fence_processing_attempt(cur, run.binding)
            finally:
                conn.commit()
        future.result(timeout=10)
    with request.scope(claimed), pytest.raises(ProcessingAuthorityLost):
        service.assert_authority(run.binding)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id=%s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 1


def test_reset_committing_before_waiting_admission_rejects_old_session(processing):
    pids = Queue()
    password_hash = hash_password("new-password")

    def admit():
        with db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            result = start_with_cursor(cur, processing)
            conn.commit()
            return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_connection() as conn, conn.cursor() as cur:
            bootstrap_admin(
                cur,
                email=processing.principal.email,
                display_name="Reset actor",
                household_name="Processing",
                household_slug="processing",
                password_hash=password_hash,
                must_rotate=True,
            )
            future = pool.submit(admit)
            try:
                wait_for_blocked(cur, conn.info.backend_pid, pids.get(timeout=5))
            finally:
                conn.commit()
        with pytest.raises(ProcessingError):
            future.result(timeout=10)


def test_admitted_browser_request_survives_waiting_password_reset_without_deadlock(processing):
    pids = Queue()

    def reset():
        with db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            bootstrap_admin(
                cur,
                email=processing.principal.email,
                display_name="Reset actor",
                household_name="Processing",
                household_slug="processing",
                password_hash=hash_password("new-password"),
                must_rotate=True,
            )
            conn.commit()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_connection() as conn, conn.cursor() as cur:
            run = start_with_cursor(cur, processing)
            future = pool.submit(reset)
            try:
                wait_for_blocked(cur, conn.info.backend_pid, pids.get(timeout=5))
            finally:
                conn.commit()
        future.result(timeout=10)
    with pytest.raises(ProcessingError):
        processing.start()
    with processing.scope(processing.claim()):
        DocumentProcessingService().assert_authority(run.binding)


def test_sibling_child_admission_does_not_hold_job_root_while_waiting_for_publication(processing):
    request = token_request(processing)
    run = request.start()
    claimed = request.claim()
    with request.scope(claimed):
        DocumentProcessingService().initialize_inventory(run.binding, request.inventory)
    pids = Queue()

    def child():
        with request.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            created = create_job_with_cursor(
                cur, job_id=uuid4(), job_type="extract", queue_name=request.queue
            )
            conn.commit()
            return created

    with ThreadPoolExecutor(max_workers=1) as pool:
        with request.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            checkpoint_repository.persist_checkpoint(cur, run.binding, request.checkpoint(run))
            future = pool.submit(child)
            try:
                wait_for_blocked(cur, conn.info.backend_pid, pids.get(timeout=5))
                # If child held the root while waiting for our document this
                # fence would deadlock. It must acquire the authority prefix first.
                cur.execute("SET LOCAL lock_timeout='2s'")
                fence_processing_attempt(cur, run.binding)
            finally:
                conn.commit()
        created = future.result(timeout=10)
    assert created.job_id != run.root_job_id
