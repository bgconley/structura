from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from uuid import uuid4

import pytest

from lib.db.connection import db_connection
from lib.jobs import JobOwnershipLost
from lib.jobs.operator_repository import cancel_job
from lib.search.indexing import header_repository, input_repository, vector_repository
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.render_commit import prepare_render_commits
from lib.storage import lock_content_hash
from tests.integration.search.indexing.conftest import asset_for, observation


def wait_for_lock(pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (pid,))
            row = cur.fetchone()
            if row and row["wait_event_type"] == "Lock":
                return
        time.sleep(0.01)
    raise AssertionError("Expected a separate connection waiting for a real database lock")


def setup_text(candidate_source):
    processing, run, claimed, service, _, _ = candidate_source
    config = index_configuration(model_mode="fixture", modalities=("text",))
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
        manifest = service.prepare(binding)
    return (
        processing,
        run,
        claimed,
        service,
        config,
        binding,
        observation(manifest.inputs[0], config),
    )


def test_build_supersession_wins_before_old_publication(candidate_source):
    processing, run, claimed, _, config, binding, value = setup_text(candidate_source)
    pids = Queue()

    def publish():
        with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            vector_repository.persist_vector(cur, binding, value)
            conn.commit()

    with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
        header_repository.start_index(cur, run.binding, request_key=uuid4(), configuration=config)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publish)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    assert_no_vectors(binding)


@pytest.mark.parametrize("revocation", ["cancel", "expire"])
def test_job_revocation_while_publisher_waits_rolls_back_domain_write(candidate_source, revocation):
    processing, _, claimed, _, _, binding, value = setup_text(candidate_source)
    pids = Queue()

    def publish():
        with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            vector_repository.persist_vector(cur, binding, value)
            conn.commit()

    with db_connection() as conn, conn.cursor() as cur:
        if revocation == "cancel":
            cancel_job(
                cur,
                job_id=claimed.state.job_id,
                household_id=processing.access.household_id,
                reason="safe",
                include_running=True,
                requested_by="test",
            )
        else:
            cur.execute(
                "SELECT id FROM pipeline_jobs WHERE id=%s FOR UPDATE", (claimed.state.job_id,)
            )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publish)
            wait_for_lock(pids.get(timeout=5))
            if revocation == "expire":
                cur.execute(
                    "UPDATE pipeline_jobs SET "
                    "lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
                    (claimed.state.job_id,),
                )
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    assert_no_vectors(binding)


def test_duplicate_document_fk_then_content_lock_does_not_invert_candidate_order(candidate_source):
    processing, run, claimed, service, checkpoint, stored = candidate_source
    config = index_configuration(model_mode="fixture", modalities=("visual",))
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
    asset = asset_for(binding, checkpoint, stored)
    pids = Queue()

    def prepare():
        with prepare_render_commits((asset,), service.storage) as prepared:
            with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
                pids.put(conn.info.backend_pid)
                input_repository.prepare_inputs(
                    cur,
                    binding,
                    (asset,),
                    commit_sources=prepared.commit_under_content_locks,
                )
                conn.commit()

    with db_connection() as conn, conn.cursor() as cur:
        # Same implicit KEY SHARE as duplicate ingestion, acquired before hash lock.
        cur.execute(
            "INSERT INTO "
            "documents(title,ingestion_source,household_id,owner_user_id,duplicate_of_document_id) "
            "VALUES ('Duplicate','web_upload',%s,%s,%s)",
            (processing.access.household_id, processing.access.user_id, processing.document_id),
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(prepare)
            wait_for_lock(pids.get(timeout=5))
            cur.execute("SET LOCAL lock_timeout='1s'")
            lock_content_hash(cur, stored.sha256)
            conn.commit()
            future.result(timeout=5)
    with processing.scope(claimed):
        assert len(service.missing_inputs(binding)) == 1


def assert_no_vectors(binding):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_index_vector_checkpoints WHERE "
            "index_generation_id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone()["n"] == 0
