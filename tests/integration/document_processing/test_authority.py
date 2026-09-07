from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from queue import Queue
from uuid import uuid4

import pytest
from psycopg.errors import RaiseException

from lib.db.connection import db_connection
from lib.document_processing import checkpoint_repository, run_repository
from lib.document_processing.authority_repository import fence_processing_attempt
from lib.document_processing.errors import ProcessingAuthorityLost, ProcessingError
from lib.document_processing.service import DocumentProcessingService
from lib.jobs import JobOwnershipLost, JobService, JobServiceError


def _row(job_id):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM pipeline_jobs WHERE id = %s", (job_id,))
        return cur.fetchone()


def _wait_for_lock(pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pid,))
            row = cur.fetchone()
            if row and row["wait_event_type"] == "Lock":
                return
        time.sleep(0.01)
    raise AssertionError("Expected the separate connection to wait for a real SQL lock")


def test_superseded_run_is_rejected_independently_of_live_claim(processing):
    service, jobs = DocumentProcessingService(), JobService()
    first = processing.start()
    claimed = processing.claim()
    with processing.scope(claimed):
        service.initialize_inventory(first.binding, processing.inventory)
    second = processing.start()
    row = _row(claimed.state.job_id)
    assert row["status"] == "running" and row["claim_token"] == claimed.claim_token
    assert row["lineage_revoked_at"] is None
    with processing.scope(claimed):
        for operation in (
            lambda: service.checkpoint(first.binding, processing.checkpoint(first)),
            lambda: service.initialize_inventory(first.binding, processing.inventory),
            lambda: service.seal(
                first.binding, processing.structure(first, [processing.checkpoint(first)])
            ),
            lambda: service.load_checkpoints(first.binding),
            lambda: jobs.create_job(job_type="extract", queue_name=processing.queue),
        ):
            with pytest.raises(JobOwnershipLost):
                operation()
    for operation in (
        lambda: jobs.heartbeat_job(
            job_id=claimed.state.job_id, claim_token=claimed.claim_token, worker_name="old"
        ),
        lambda: jobs.complete_job(job_id=claimed.state.job_id, claim_token=claimed.claim_token),
        lambda: jobs.fail_job(
            job_id=claimed.state.job_id,
            claim_token=claimed.claim_token,
            error_class="RuntimeError",
            message="old",
        ),
    ):
        with pytest.raises(JobOwnershipLost):
            operation()
    assert processing.claim().state.job_id == second.root_job_id
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id = %s",
            (first.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT canonical_asset_id FROM documents WHERE id = %s", (processing.document_id,)
        )
        assert cur.fetchone()["canonical_asset_id"] == processing.asset_id


def test_request_idempotency_cancel_and_manual_retry_do_not_revive_authority(processing):
    key = uuid4()
    first = processing.start(request_key=key)
    assert processing.start(request_key=key) == first
    with pytest.raises(ProcessingError):
        processing.start(request_key=key, original_sha256="f" * 64)
    DocumentProcessingService().cancel(first.binding, processing.access)
    assert (
        JobService().claim_next_job_record(worker_name="late", queue_name=processing.queue) is None
    )
    jobs = JobService()
    jobs.cancel_job(job_id=first.root_job_id, reason="Cancelled run")
    with pytest.raises(JobServiceError):
        jobs.retry_job(job_id=first.root_job_id)
    assert processing.start(request_key=key).status == "cancelled"
    second = processing.start()
    assert second.generation == first.generation + 1


def test_concurrent_same_request_creates_one_run_and_one_root(processing):
    key = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(processing.start, request_key=key)
        second = pool.submit(processing.start, request_key=key)
        assert first.result(timeout=5) == second.result(timeout=5)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_processing_runs WHERE document_id = %s",
            (processing.document_id,),
        )
        assert cur.fetchone()["n"] == 1
        cur.execute(
            "SELECT count(*) AS n FROM audit_events WHERE document_id = %s "
            "AND event_name = 'processing.requested'",
            (processing.document_id,),
        )
        assert cur.fetchone()["n"] == 1


def test_request_requires_live_document_authority_and_matching_original(processing):
    with pytest.raises(ProcessingError):
        processing.start(principal=replace(processing.principal, user_id=uuid4()))
    with pytest.raises(ProcessingError):
        processing.start(original_asset_id=uuid4())
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT processing_generation FROM documents WHERE id = %s",
            (processing.document_id,),
        )
        assert cur.fetchone()["processing_generation"] == 0


def test_bindings_are_inherited_and_cannot_cross_documents_or_be_retargeted(processing):
    first = processing.start()
    claimed = processing.claim()
    assert claimed.processing_run_id == first.binding.processing_run_id
    assert claimed.parse_generation_id == first.binding.parse_generation_id
    jobs = JobService()
    with processing.scope(claimed):
        child = jobs.create_job(job_type="extract", queue_name=processing.queue)
        with pytest.raises(JobServiceError):
            jobs.create_job(
                job_type="extract", processing_run_id=uuid4(), queue_name=processing.queue
            )
    assert _row(child.job_id)["processing_run_id"] == first.binding.processing_run_id
    with db_connection() as conn, conn.cursor() as cur:
        with pytest.raises(RaiseException, match="immutable"):
            cur.execute(
                "UPDATE pipeline_jobs SET processing_run_id = NULL, parse_generation_id = NULL "
                "WHERE id = %s",
                (child.job_id,),
            )
        conn.rollback()
    with pytest.raises(JobOwnershipLost):
        jobs.create_job(
            job_type="extract",
            document_id=processing.document_id,
            household_id=processing.access.household_id,
            processing_run_id=first.binding.processing_run_id,
            parse_generation_id=uuid4(),
        )


def test_candidate_commit_serializes_before_new_request_without_losing_history(processing):
    first = processing.start()
    claimed = processing.claim()
    service = DocumentProcessingService()
    with processing.scope(claimed):
        service.initialize_inventory(first.binding, processing.inventory)
    pids = Queue()

    def replace_run():
        with db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            run = run_repository.start_parse_run(
                cur,
                document_id=processing.document_id,
                principal=processing.principal,
                original_asset_id=processing.asset_id,
                original_sha256=processing.original_sha256,
                request_key=uuid4(),
                configuration=processing.configuration,
                queue_name=processing.queue,
            )
            conn.commit()
            return run

    with ThreadPoolExecutor(max_workers=1) as pool:
        with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            checkpoint_repository.persist_checkpoint(
                cur, first.binding, processing.checkpoint(first)
            )
            future = pool.submit(replace_run)
            _wait_for_lock(pids.get(timeout=5))
            fence_processing_attempt(cur, first.binding)
            conn.commit()
        second = future.result(timeout=5)
    assert second.generation == first.generation + 1
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id = %s",
            (first.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 1


def test_new_request_commit_fences_waiting_old_candidate_after_lock(processing):
    first = processing.start()
    claimed = processing.claim()
    with processing.scope(claimed):
        DocumentProcessingService().initialize_inventory(first.binding, processing.inventory)
    pids = Queue()

    def old_candidate():
        with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            checkpoint_repository.persist_checkpoint(
                cur, first.binding, processing.checkpoint(first)
            )
            fence_processing_attempt(cur, first.binding)
            conn.commit()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_connection() as conn, conn.cursor() as cur:
            run_repository.start_parse_run(
                cur,
                document_id=processing.document_id,
                principal=processing.principal,
                original_asset_id=processing.asset_id,
                original_sha256=processing.original_sha256,
                request_key=uuid4(),
                configuration=processing.configuration,
                queue_name=processing.queue,
            )
            future = pool.submit(old_candidate)
            _wait_for_lock(pids.get(timeout=5))
            conn.commit()
        with pytest.raises(ProcessingAuthorityLost):
            future.result(timeout=5)
