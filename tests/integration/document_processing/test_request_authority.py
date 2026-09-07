from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from psycopg.errors import RaiseException

from lib.auth import AuthService
from lib.db.connection import db_connection
from lib.document_processing.errors import ProcessingError
from lib.document_processing.service import DocumentProcessingService
from lib.jobs import JobOwnershipLost, JobService

from .authority_cases import make_granted_member, revoke, token_request


@pytest.mark.parametrize("scopes", [(), ("documents:read",), ("documents:review",), ("unknown",)])
def test_read_review_unknown_and_empty_token_cannot_start(processing, scopes):
    request = token_request(processing, scopes)
    with pytest.raises(ProcessingError):
        request.start()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT processing_generation FROM documents WHERE id=%s", (request.document_id,)
        )
        assert cur.fetchone()["processing_generation"] == 0


@pytest.mark.parametrize("scopes", [("documents:write",), ("admin",), ("admin:*",)])
def test_write_capable_token_and_descendant_keep_exact_origin(processing, scopes):
    request = token_request(processing, scopes)
    run = request.start()
    claimed = request.claim()
    service = DocumentProcessingService()
    with request.scope(claimed):
        service.initialize_inventory(run.binding, request.inventory)
        service.checkpoint(run.binding, request.checkpoint(run))
        child = JobService().create_job(job_type="extract", queue_name=request.queue)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM document_processing_runs WHERE id=%s", (run.binding.processing_run_id,)
        )
        row = cur.fetchone()
        assert row["origin_kind"] == "api_token"
        assert row["origin_api_token_id"] == request.principal.api_token_id
        assert row["origin_scope_ceiling"] == list(scopes)
        cur.execute("SELECT processing_run_id FROM pipeline_jobs WHERE id=%s", (child.job_id,))
        assert cur.fetchone()["processing_run_id"] == run.binding.processing_run_id


@pytest.mark.parametrize("change", ["logout", "expired", "password_reset", "session_deleted"])
def test_durable_browser_request_survives_session_lifetime(processing, change):
    run = processing.start()
    if change == "logout":
        AuthService().revoke_authenticated_session(processing.principal)
    elif change == "password_reset":
        AuthService().bootstrap_admin(
            email=processing.principal.email, password="new-password", household_name="Processing"
        )
    else:
        with db_connection() as conn, conn.cursor() as cur:
            if change == "expired":
                cur.execute(
                    "UPDATE sessions SET expires_at=clock_timestamp()-interval '1 second' "
                    "WHERE id=%s",
                    (processing.principal.session_id,),
                )
            else:
                cur.execute("DELETE FROM sessions WHERE id=%s", (processing.principal.session_id,))
    # The same credential cannot authorize a new request, but an admitted durable
    # request remains authorized by its enabled actor, membership and resource.
    with pytest.raises(ProcessingError):
        processing.start()
    claimed = processing.claim()
    service = DocumentProcessingService()
    with processing.scope(claimed):
        service.assert_authority(run.binding)
        service.initialize_inventory(run.binding, processing.inventory)
        checkpoint = processing.checkpoint(run)
        service.checkpoint(run.binding, checkpoint)
        service.seal(run.binding, processing.structure(run, [checkpoint]))


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
        "token_expired",
        "token_missing",
        "token_read_only",
    ],
)
def test_revocation_between_model_and_publication_blocks_all_bound_outputs(processing, change):
    request = token_request(processing) if change.startswith("token_") else processing
    _, grant_id = make_granted_member(request)
    run = request.start()
    claimed = request.claim()
    service = DocumentProcessingService()
    checkpoint = request.checkpoint(run)
    with request.scope(claimed):
        service.initialize_inventory(run.binding, request.inventory)
        service.assert_authority(run.binding)  # Successful pre-model admission.
        with db_connection() as conn, conn.cursor() as cur:
            revoke(cur, request, change, grant_id=grant_id)
        for operation in (
            lambda: service.assert_authority(run.binding),
            lambda: service.checkpoint(run.binding, checkpoint),
            lambda: service.seal(run.binding, request.structure(run, [checkpoint])),
            lambda: service.load_checkpoints(run.binding),
            lambda: service.initialize_inventory(run.binding, request.inventory),
            lambda: JobService().create_job(job_type="extract", queue_name=request.queue),
        ):
            with pytest.raises(JobOwnershipLost):
                operation()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id=%s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT state FROM document_parse_generations WHERE id=%s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone()["state"] == "building"
        cur.execute(
            "SELECT count(*) AS n FROM pipeline_jobs WHERE parent_job_id=%s", (run.root_job_id,)
        )
        assert cur.fetchone()["n"] == 0


def test_origin_is_immutable_and_request_key_cannot_move_to_another_credential(processing):
    request = token_request(processing)
    key = uuid4()
    run = request.start(request_key=key)
    assert request.start(request_key=key) == run
    other = token_request(processing)
    with pytest.raises(ProcessingError, match="different intent"):
        other.start(request_key=key)
    with db_connection() as conn, conn.cursor() as cur:
        with pytest.raises(RaiseException, match="immutable"):
            cur.execute(
                "UPDATE document_processing_runs SET origin_scope_ceiling=ARRAY['admin'] "
                "WHERE id=%s",
                (run.binding.processing_run_id,),
            )


def test_current_token_cannot_be_spoofed_or_gain_a_request_from_old_read_scope(processing):
    reader = token_request(processing, ("documents:read",))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE api_tokens SET scopes=ARRAY['documents:write'] WHERE id=%s",
            (reader.principal.api_token_id,),
        )
    with pytest.raises(ProcessingError):
        reader.start()  # Authenticated request's old ceiling still excludes write.
    writer = token_request(processing)
    for principal in (
        replace(writer.principal, api_token_id=uuid4()),
        replace(writer.principal, user_id=uuid4()),
        replace(writer.principal, household_id=uuid4()),
        replace(writer.principal, session_id=processing.principal.session_id),
    ):
        with pytest.raises(ProcessingError):
            writer.start(principal=principal)


def test_revoked_token_request_is_not_claimed_and_legacy_unbound_queue_is_unchanged(processing):
    request = token_request(processing)
    request.start()
    with db_connection() as conn, conn.cursor() as cur:
        revoke(cur, request, "token_revoked")
    jobs = JobService()
    assert jobs.claim_next_job_record(worker_name="denied", queue_name=request.queue) is None
    unbound = jobs.create_job(job_type="extract", queue_name=request.queue)
    assert request.claim().state.job_id == unbound.job_id
