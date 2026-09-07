"""Retained reconstruction uses today's reader ACL, not yesterday's job lease."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from queue import Queue
from uuid import uuid4

import pytest

from lib.auth import AuthService
from lib.auth.authorization_policy import AuthorizationError
from lib.auth.request_authority import RequestCredential
from lib.db.connection import db_connection
from lib.extraction.native_claims import read_repository
from lib.extraction.native_claims.service import NativeClaimService
from lib.jobs import JobService
from tests.integration.document_processing.authority_cases import make_granted_member, token_request
from tests.integration.native_claims.test_currency import populated
from tests.integration.search.indexing.test_authority_races import wait_for_lock


def test_completed_producer_and_later_reparse_keep_identical_historical_rebuild(
    native_source, monkeypatch
):
    processing, _, claimed, binding, _ = populated(native_source)
    service = NativeClaimService()
    credential = RequestCredential.from_principal(processing.principal)
    before = service.rebuild(binding, credential=credential)
    assert (
        JobService()
        .complete_job(job_id=claimed.state.job_id, claim_token=claimed.claim_token)
        .status
        == "succeeded"
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Retained rebuild cannot reparse provider output or use write authority"
        )

    monkeypatch.setattr("lib.extraction.claims.claims_from_region_envelope", forbidden)
    monkeypatch.setattr(
        "lib.document_parsing.model_output.PageParseOutput.model_validate_json", forbidden
    )
    monkeypatch.setattr("lib.extraction.native_claims.authority_repository.lock_source", forbidden)
    assert service.rebuild(binding, credential=credential) == before
    later = processing.start()
    assert later.binding.processing_run_id != binding.processing.processing_run_id
    assert service.rebuild(binding, credential=credential) == before
    # A separate, currently authorized read token needs no producer-job context.
    reader = token_request(processing, scopes=("documents:read",))
    assert (
        service.rebuild(binding, credential=RequestCredential.from_principal(reader.principal))
        == before
    )


def test_retained_rebuild_requires_live_reader_session(native_source):
    processing, _, _, binding, _ = populated(native_source)
    credential = RequestCredential.from_principal(processing.principal)
    AuthService().revoke_authenticated_session(processing.principal)
    with pytest.raises(AuthorizationError):
        NativeClaimService().rebuild(binding, credential=credential)


def test_retained_rebuild_fails_closed_for_foreign_household(native_source):
    processing, _, _, binding, _ = populated(native_source)
    credential = replace(
        RequestCredential.from_principal(processing.principal), household_id=uuid4()
    )
    with pytest.raises(AuthorizationError):
        NativeClaimService().rebuild(binding, credential=credential)


def test_reader_waiting_for_refile_rechecks_document_acl(native_source):
    processing, _, _, binding, _ = populated(native_source)
    make_granted_member(processing)
    credential = RequestCredential.from_principal(processing.principal)
    assert NativeClaimService().rebuild(binding, credential=credential)["claim_count"] == 2
    pids = Queue()

    def read_waiting():
        with db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            return read_repository.read_sealed(cur, binding, credential)

    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET acl_mode='private' WHERE id=%s", (processing.document_id,)
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(read_waiting)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            with pytest.raises(AuthorizationError):
                future.result(timeout=5)
