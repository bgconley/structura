from concurrent.futures import ThreadPoolExecutor
from queue import Queue

import pytest

from lib.auth import AuthService
from lib.db.connection import db_connection
from lib.document_processing import run_repository
from lib.extraction.native_claims import page_repository
from lib.extraction.native_claims.service import NativeClaimService
from lib.jobs import JobOwnershipLost
from lib.jobs.operator_repository import cancel_job
from tests.integration.document_processing.authority_cases import revoke, token_request
from tests.integration.native_claims.conftest import page_request, setup_source
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


def publisher(processing, claimed, binding, checkpoint, pids):
    with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
        pids.put(conn.info.backend_pid)
        page_repository.persist_page(cur, binding, page_request(checkpoint))
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
    ],
)
def test_revocation_committing_while_publication_waits_rejects_all_claims(processing, change):
    if change.startswith("token_"):
        processing = token_request(processing)
    processing, _, claimed, binding, checkpoints = setup_source(processing)
    pids = Queue()
    with db_connection() as conn, conn.cursor() as cur:
        revoke(cur, processing, change)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publisher, processing, claimed, binding, checkpoints[0], pids)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    assert_empty(binding)


def test_cancelled_run_wins_before_waiting_claim_publication(native_source):
    processing, _, claimed, binding, checkpoints = native_source
    pids = Queue()
    with db_connection() as conn, conn.cursor() as cur:
        run_repository.cancel_parse_run(cur, binding.processing, processing.access)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publisher, processing, claimed, binding, checkpoints[0], pids)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    assert_empty(binding)


def test_job_cancel_after_provisional_claim_insert_rolls_back_page_and_rows(native_source):
    processing, _, claimed, binding, checkpoints = native_source
    pids = Queue()
    with db_connection() as conn, conn.cursor() as cur:
        cancel_job(
            cur,
            job_id=claimed.state.job_id,
            household_id=processing.access.household_id,
            reason="test cancellation",
            include_running=True,
            requested_by="test",
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publisher, processing, claimed, binding, checkpoints[0], pids)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    assert_empty(binding)


def test_new_run_cannot_reanimate_old_claim_currency(native_source):
    processing, _, claimed, binding, checkpoints = native_source
    processing.start()
    with processing.scope(claimed), pytest.raises(JobOwnershipLost):
        NativeClaimService().checkpoint(binding, page_request(checkpoints[0]))
    assert_empty(binding)


def test_browser_logout_preserves_admitted_durable_claim_work(native_source):
    processing, _, claimed, binding, checkpoints = native_source
    AuthService().revoke_authenticated_session(processing.principal)
    service = NativeClaimService()
    with processing.scope(claimed):
        service.checkpoint(binding, page_request(checkpoints[0]))
        assert service.seal(binding)["claim_count"] == 2


def test_concurrent_identical_page_replay_produces_one_inventory(native_source):
    processing, _, claimed, binding, checkpoints = native_source
    pids = Queue()
    with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
        page_repository.persist_page(cur, binding, page_request(checkpoints[0]))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publisher, processing, claimed, binding, checkpoints[0], pids)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            future.result(timeout=5)
    with processing.scope(claimed):
        assert NativeClaimService().seal(binding)["claim_count"] == 2
