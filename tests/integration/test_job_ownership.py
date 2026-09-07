from __future__ import annotations

import json
import os
from threading import Event
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.documents.canonical_parse import mark_parse_failed
from lib.jobs import JobOwnershipLost, JobService
from lib.jobs.lifecycle_repository import recover_expired_running_jobs
from lib.jobs.ownership import JobAttempt, fence_current_job, job_attempt_scope
from lib.jobs.public_errors import safe_job_failure

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Requires an isolated database migrated through 091.",
)


@pytest.fixture
def job_scope(monkeypatch):
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    jobs = JobService()
    queue = f"ownership-{uuid4()}"
    state = jobs.create_job(job_type="extract", queue_name=queue)
    first = jobs.claim_next_job_record(worker_name="first", queue_name=queue)
    assert first and first.state.job_id == state.job_id
    yield jobs, queue, first
    get_settings.cache_clear()


def expire(job_id):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_jobs SET lease_expires_at = "
            "clock_timestamp() - interval '1 second' WHERE id = %s",
            (job_id,),
        )


def test_reclaimed_attempt_cannot_renew_complete_fail_or_publish(job_scope) -> None:
    jobs, queue, first = job_scope
    expire(first.state.job_id)
    second = jobs.claim_next_job_record(worker_name="second", queue_name=queue)
    assert second and second.claim_token != first.claim_token
    with pytest.raises(JobOwnershipLost):
        jobs.heartbeat_job(
            job_id=first.state.job_id, claim_token=first.claim_token, worker_name="first"
        )
    with pytest.raises(JobOwnershipLost):
        jobs.complete_job(job_id=first.state.job_id, claim_token=first.claim_token)
    with pytest.raises(JobOwnershipLost):
        jobs.fail_job(
            job_id=first.state.job_id,
            claim_token=first.claim_token,
            error_class="RuntimeError",
            message="stale failure",
        )

    owner = AuthService().bootstrap_admin(
        email=f"ownership-{uuid4()}@example.com", password="minimum8", household_name="Ownership"
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents (title, ingestion_source, household_id, owner_user_id) "
            "VALUES ('Original','web_upload',%s,%s) RETURNING id",
            (owner.household_id, owner.user_id),
        )
        document_id = cur.fetchone()["id"]

    # Exercise a real repository publication boundary, including its independent commit.
    with (
        pytest.raises(JobOwnershipLost),
        job_attempt_scope(JobAttempt(first.state.job_id, first.claim_token), Event()),
    ):
        mark_parse_failed(
            document_id=document_id,
            error_class="RuntimeError",
            message="Stale parse failure",
            job_id=first.state.job_id,
        )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT metadata_json FROM documents WHERE id = %s", (document_id,))
        assert "phase3" not in cur.fetchone()["metadata_json"]

    # Domain mutation happens first, then the fence must abort the SAME transaction.
    with (
        pytest.raises(JobOwnershipLost),
        job_attempt_scope(JobAttempt(first.state.job_id, first.claim_token), Event()),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "UPDATE documents SET title = 'Stale publication' WHERE id = %s", (document_id,)
        )
        fence_current_job(cur)
        conn.commit()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT title FROM documents WHERE id = %s", (document_id,))
        assert cur.fetchone()["title"] == "Original"

    with (
        job_attempt_scope(JobAttempt(second.state.job_id, second.claim_token), Event()),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            "UPDATE documents SET title = 'Current publication' WHERE id = %s", (document_id,)
        )
        fence_current_job(cur)
        conn.commit()
    assert (
        jobs.complete_job(job_id=second.state.job_id, claim_token=second.claim_token).status
        == "succeeded"
    )
    assert "claim_token" not in jobs.get_job(second.state.job_id).model_dump_json()


def test_expired_lease_is_rejected_in_transaction_started_before_expiry(job_scope) -> None:
    _jobs, _queue, first = job_scope
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT now()")
        # The publication transaction now predates the externally expired lease.
        expire(first.state.job_id)
        with job_attempt_scope(JobAttempt(first.state.job_id, first.claim_token), Event()):
            with pytest.raises(JobOwnershipLost):
                fence_current_job(cur)


def test_cancel_revokes_ownership_before_domain_publication(job_scope) -> None:
    jobs, _queue, first = job_scope
    jobs.cancel_job(job_id=first.state.job_id, reason="Test cancellation", include_running=True)
    with (
        pytest.raises(JobOwnershipLost),
        job_attempt_scope(JobAttempt(first.state.job_id, first.claim_token), Event()),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        fence_current_job(cur)
    assert jobs.get_job(first.state.job_id).status == "cancelled"


@pytest.mark.parametrize("transition", ["cancel", "expire"])
def test_terminal_event_replaces_stale_timeout_and_private_metadata(job_scope, transition) -> None:
    jobs, queue, first = job_scope
    private = "private patient text /private/source.pdf token=secret"
    old_error = {**safe_job_failure("ModelTimeoutError", private), "details": {"raw": private}}
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE pipeline_jobs SET error_json = %s::jsonb WHERE id = %s",
            (Jsonb(old_error), first.state.job_id),
        )
    if transition == "cancel":
        jobs.cancel_job(
            job_id=first.state.job_id, reason=private, requested_by=private, include_running=True
        )
        expected_code = "job_cancelled"
    else:
        expire(first.state.job_id)
        with db_connection() as conn, conn.cursor() as cur:
            assert recover_expired_running_jobs(cur, queue_name=queue, document_id=None) == 1
        expected_code = "worker_lease_expired"
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT error_json FROM pipeline_jobs WHERE id = %s", (first.state.job_id,))
        event = cur.fetchone()["error_json"]
    assert event["public_code"] == expected_code
    assert event["error_id"] != old_error["error_id"]
    assert event["details"] == {}
    assert private not in json.dumps(event)
    assert "did not respond in time" not in jobs.get_job(first.state.job_id).error_message
