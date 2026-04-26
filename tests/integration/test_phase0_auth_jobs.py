from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("psycopg")

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.jobs import JobService, record_service_health


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 0 auth/job tests.",
)
def test_phase0_auth_session_protection_jobs_and_service_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase0-{unique}@example.com"
    password = "minimum8"
    bootstrap = AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name="Phase 0 Admin",
        household_name=f"Phase 0 {unique}",
        must_rotate=True,
    )

    app = create_app()
    client = TestClient(app)

    assert client.get("/api/v1/documents").status_code == 401
    assert client.get(f"/api/v1/assets/{uuid.uuid4()}").status_code == 401
    assert client.get("/api/v1/migrations/baseline").status_code == 401

    invalid_login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": "not-an-email", "password": password},
    )
    assert invalid_login.status_code == 422

    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    assert login.json()["authMethod"] == "password"
    assert login.json()["passwordRotationRequired"] is True
    assert "structura_session" in client.cookies
    assert "structura_csrf" in client.cookies

    assert client.get("/api/v1/auth/session").status_code == 200
    assert client.get("/api/v1/migrations/baseline").status_code == 200
    assert client.get("/api/v1/documents").json() == {"items": [], "total": 0}
    assert client.get(f"/api/v1/assets/{uuid.uuid4()}").status_code == 404

    magic = client.post(
        "/api/v1/auth/magic-links",
        json={"email": email, "purpose": "bootstrap"},
    )
    assert magic.status_code == 202
    assert magic.json()["accepted"] is True
    assert "token" in magic.json()

    queue_name = f"phase0-{unique}"
    job_service = JobService()
    retryable_job = job_service.create_job(
        job_type="ingest",
        household_id=bootstrap.household_id,
        payload={"document_id": "retryable-placeholder"},
        queue_name=queue_name,
    )
    claimed = job_service.claim_next_job(worker_name="phase0-test", queue_name=queue_name)
    assert claimed
    assert claimed.job_id == retryable_job.job_id
    failed_retryable = job_service.fail_job(
        job_id=retryable_job.job_id,
        error_class="Phase0Retryable",
        message="exercise delayed retry",
        retryable=True,
    )
    assert failed_retryable.status == "failed"
    assert job_service.claim_next_job(worker_name="phase0-test", queue_name=queue_name) is None

    job = job_service.create_job(
        job_type="ingest",
        household_id=bootstrap.household_id,
        payload={"document_id": "placeholder"},
    )
    failed = JobService().fail_job(
        job_id=job.job_id,
        error_class="Phase0Test",
        message="exercise retry",
        retryable=False,
    )
    assert failed.status == "dead_letter"
    assert client.get(f"/api/v1/jobs/{job.job_id}").json()["status"] == "dead_letter"
    assert client.get("/api/v1/admin/jobs", params={"status": "dead_letter"}).status_code == 200

    retry_without_csrf = client.post(f"/api/v1/admin/jobs/{job.job_id}/retry")
    assert retry_without_csrf.status_code == 403
    retry = client.post(
        f"/api/v1/admin/jobs/{job.job_id}/retry",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
    )
    assert retry.status_code == 202
    assert retry.json()["status"] == "queued"
    assert job_service.claim_next_job(worker_name="phase0-test") is not None

    record_service_health(service_name="worker-phase0-test", status="ok", metrics={"jobs": 1})
    health = client.get("/api/v1/admin/service-health")
    assert health.status_code == 200
    assert any(item["service_name"] == "worker-phase0-test" for item in health.json()["items"])

    logout = client.delete(
        "/api/v1/auth/session",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
    )
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 0 auth/job tests.",
)
def test_phase0_job_routes_are_household_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    password = "minimum8"
    owner = AuthService().bootstrap_admin(
        email=f"phase0-job-owner-{unique}@example.com",
        password=password,
        display_name="Phase 0 Job Owner",
        household_name=f"Phase 0 Job Owner {unique}",
        must_rotate=False,
    )
    other_email = f"phase0-job-other-{unique}@example.com"
    AuthService().bootstrap_admin(
        email=other_email,
        password=password,
        display_name="Phase 0 Job Other",
        household_name=f"Phase 0 Job Other {unique}",
        must_rotate=False,
    )

    job = JobService().create_job(
        job_type="ingest",
        household_id=owner.household_id,
        payload={"document_id": "household-scope-placeholder"},
    )

    other = TestClient(create_app())
    login = other.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": other_email, "password": password},
    )
    assert login.status_code == 201
    assert other.get(f"/api/v1/jobs/{job.job_id}").status_code == 404
    listed = other.get("/api/v1/admin/jobs")
    assert listed.status_code == 200
    assert str(job.job_id) not in {item["jobId"] for item in listed.json()["items"]}


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 0 auth/job tests.",
)
def test_phase0_expired_running_jobs_are_recoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    password = "minimum8"
    bootstrap = AuthService().bootstrap_admin(
        email=f"phase0-stale-job-{unique}@example.com",
        password=password,
        display_name="Phase 0 Stale Job Admin",
        household_name=f"Phase 0 Stale Job {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={
            "method": "password",
            "email": f"phase0-stale-job-{unique}@example.com",
            "password": password,
        },
    )
    assert login.status_code == 201

    job_service = JobService()
    queue_name = f"phase0-stale-{unique}"
    stale = job_service.create_job(
        job_type="ingest",
        household_id=bootstrap.household_id,
        payload={"document_id": "stale-running-placeholder"},
        queue_name=queue_name,
        max_attempts=3,
    )
    claimed = job_service.claim_next_job_record(
        worker_name="phase0-stale-worker",
        queue_name=queue_name,
        lease_seconds=1,
    )
    assert claimed
    assert claimed.state.job_id == stale.job_id
    _expire_job_lease(stale.job_id)

    reclaimed = job_service.claim_next_job_record(
        worker_name="phase0-stale-worker-2",
        queue_name=queue_name,
    )
    assert reclaimed
    assert reclaimed.state.job_id == stale.job_id
    assert reclaimed.state.status == "running"

    manual = job_service.create_job(
        job_type="ingest",
        household_id=bootstrap.household_id,
        payload={"document_id": "manual-retry-stale-placeholder"},
        queue_name=queue_name,
        max_attempts=3,
    )
    manual_claim = job_service.claim_next_job_record(
        worker_name="phase0-manual-stale-worker",
        queue_name=queue_name,
        lease_seconds=1,
    )
    assert manual_claim
    assert manual_claim.state.job_id == manual.job_id
    _expire_job_lease(manual.job_id)

    retry = client.post(
        f"/api/v1/admin/jobs/{manual.job_id}/retry",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
    )
    assert retry.status_code == 202
    assert retry.json()["status"] == "queued"
    retried_claim = job_service.claim_next_job_record(
        worker_name="phase0-manual-stale-worker-2",
        queue_name=queue_name,
    )
    assert retried_claim
    assert retried_claim.state.job_id == manual.job_id


def _expire_job_lease(job_id: uuid.UUID) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pipeline_jobs
                SET lease_expires_at = now() - interval '1 second'
                WHERE id = %s
                """,
                (job_id,),
            )
        conn.commit()


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 0 auth/job tests.",
)
def test_phase0_auth_respects_configured_cookie_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_SESSION_COOKIE_NAME", "custom_structura_session")
    monkeypatch.setenv("STRUCTURA_CSRF_COOKIE_NAME", "custom_structura_csrf")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase0-cookie-{unique}@example.com"
    password = "minimum8"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name="Phase 0 Cookie Admin",
        household_name=f"Phase 0 Cookie {unique}",
        must_rotate=False,
    )

    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )

    assert login.status_code == 201
    assert login.json()["sessionCookieName"] == "custom_structura_session"
    assert login.json()["csrfCookieName"] == "custom_structura_csrf"
    assert "custom_structura_session" in client.cookies
    assert "custom_structura_csrf" in client.cookies
    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    assert session.json()["csrfCookieName"] == "custom_structura_csrf"

    logout = client.delete(
        "/api/v1/auth/session",
        headers={"X-CSRF-Token": client.cookies["custom_structura_csrf"]},
    )
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401
