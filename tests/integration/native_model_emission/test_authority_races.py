from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from uuid import uuid4

import pytest

from lib.auth import AuthService
from lib.db.connection import db_connection
from lib.document_processing import run_repository
from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.model_emission import page_repository, read_repository
from lib.extraction.native_claims.model_emission.configuration import installed_configuration
from lib.extraction.native_claims.model_emission.service import NativeModelEmissionService
from lib.jobs import JobOwnershipLost
from lib.jobs.operator_repository import cancel_job
from lib.jobs.ownership import JobAttempt, job_attempt_scope
from tests.integration.document_processing.authority_cases import (
    make_granted_member,
    revoke,
    token_request,
)
from tests.integration.native_model_emission.conftest import setup_source
from tests.integration.search.indexing.test_authority_races import wait_for_lock


def assert_empty(binding):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM extraction_claims WHERE native_claim_set_id=%s", (binding.claim_set_id,)
        )
        assert cur.fetchall() == []
        cur.execute(
            "SELECT page_number FROM native_claim_page_checkpoints WHERE claim_set_id=%s",
            (binding.claim_set_id,),
        )
        assert cur.fetchall() == []
        cur.execute("SELECT state FROM native_claim_sets WHERE id=%s", (binding.claim_set_id,))
        assert cur.fetchone()["state"] == "building"


def publish(processing, claimed, binding, pids, operation="page"):
    implementation = installed_configuration()
    with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
        pids.put(conn.info.backend_pid)
        if operation == "page":
            page_repository.persist_page(cur, binding, 1, implementation=implementation)
        else:
            read_repository.seal_set(cur, binding, implementation=implementation)
        conn.commit()


@pytest.mark.parametrize(
    "change",
    [
        "disabled",
        "membership_removed",
        "viewer",
        "token_revoked",
        "token_expired",
        "token_read_only",
        "refile",
    ],
)
def test_revocation_or_refile_committing_during_wait_rolls_back_entire_page(processing, change):
    if change.startswith("token_"):
        processing = token_request(processing)
    if change == "refile":
        make_granted_member(processing)
    processing, _, claimed, binding, _ = setup_source(processing)
    pids = Queue()
    with db_connection() as conn, conn.cursor() as cur:
        if change == "refile":
            cur.execute(
                "UPDATE documents SET acl_mode='private' WHERE id=%s", (processing.document_id,)
            )
        else:
            revoke(cur, processing, change)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publish, processing, claimed, binding, pids)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    assert_empty(binding)


def test_cancel_after_provisional_rows_blocks_final_job_fence(model_source):
    processing, _, claimed, binding, _ = model_source
    pids = Queue()
    with db_connection() as conn, conn.cursor() as cur:
        cancel_job(
            cur,
            job_id=claimed.state.job_id,
            household_id=processing.access.household_id,
            reason="controlled cancel",
            include_running=True,
            requested_by="test",
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publish, processing, claimed, binding, pids)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    assert_empty(binding)


def test_cancelled_run_prevents_waiting_page_or_seal(model_source):
    processing, _, claimed, binding, _ = model_source
    with processing.scope(claimed):
        NativeModelEmissionService().checkpoint(binding, 1)
    pids = Queue()
    with db_connection() as conn, conn.cursor() as cur:
        run_repository.cancel_parse_run(cur, binding.processing, processing.access)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publish, processing, claimed, binding, pids, "seal")
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT state FROM native_claim_sets WHERE id=%s", (binding.claim_set_id,))
        assert cur.fetchone()["state"] == "building"


def test_concurrent_replay_keeps_one_page_and_five_physical_claims(model_source):
    processing, _, claimed, binding, _ = model_source
    pids = Queue()
    implementation = installed_configuration()
    with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
        page_repository.persist_page(cur, binding, 1, implementation=implementation)
        cur.execute(
            "SELECT id FROM extraction_claims WHERE native_claim_set_id=%s ORDER BY id",
            (binding.claim_set_id,),
        )
        before = cur.fetchall()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publish, processing, claimed, binding, pids)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            future.result(timeout=5)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM extraction_claims WHERE native_claim_set_id=%s ORDER BY id",
            (binding.claim_set_id,),
        )
        assert cur.fetchall() == before and len(before) == 5


def test_browser_logout_preserves_admitted_model_claim_job(model_source):
    processing, _, claimed, binding, _ = model_source
    AuthService().revoke_authenticated_session(processing.principal)
    with processing.scope(claimed):
        NativeModelEmissionService().checkpoint(binding, 1)
        assert NativeModelEmissionService().seal(binding)["claim_count"] == 5


def test_superseded_run_cannot_reanimate_the_same_set(model_source):
    processing, _, claimed, binding, _ = model_source
    processing.start()
    with processing.scope(claimed), pytest.raises(JobOwnershipLost):
        NativeModelEmissionService().checkpoint(binding, 1)


def test_different_producer_cannot_import_existing_set(model_source):
    _, _, claimed, binding, _ = model_source
    wrong = JobAttempt(uuid4(), claimed.claim_token)
    with job_attempt_scope(wrong, Event()), pytest.raises(NativeClaimError, match="bound producer"):
        NativeModelEmissionService().checkpoint(binding, 1)
    assert_empty(binding)
