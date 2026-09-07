from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.jobs import JobService

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"), reason="Isolated database required"
)

PRIVATE = "/srv/structura/patient-private.pdf model-private-response token=private-test-secret"


def test_persisted_failure_and_legacy_job_api_do_not_expose_private_text(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    try:
        owner = AuthService().bootstrap_admin(
            email=f"error-privacy-{uuid4()}@example.com",
            password="minimum8",
            household_name="Error privacy",
        )
        jobs = JobService()
        queue = f"privacy-{uuid4()}"
        job = jobs.create_job(job_type="extract", household_id=owner.household_id, queue_name=queue)
        claimed = jobs.claim_next_job_record(queue_name=queue, worker_name="privacy-test")
        assert claimed and claimed.state.job_id == job.job_id
        jobs.fail_job(
            job_id=job.job_id,
            claim_token=claimed.claim_token,
            error_class="ModelTimeoutError",
            message=PRIVATE,
            details={"taxonomy_code": PRIVATE, "traceback": PRIVATE},
        )
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT error_json FROM pipeline_jobs WHERE id=%s", (job.job_id,))
            assert PRIVATE not in json.dumps(cur.fetchone()["error_json"])
            cur.execute(
                "UPDATE pipeline_jobs SET error_json=%s, result_json=%s WHERE id=%s",
                (
                    Jsonb({"message": PRIVATE, "last_error": PRIVATE}),
                    Jsonb({"error_message": PRIVATE, "page_count": 2}),
                    job.job_id,
                ),
            )
        with TestClient(create_app()) as client:
            login = client.post(
                "/api/v1/auth/session",
                json={
                    "method": "password",
                    "email": owner.email,
                    "password": "minimum8",
                    "householdId": str(owner.household_id),
                },
            )
            assert login.status_code == 201
            response = client.get(f"/api/v1/jobs/{job.job_id}")
            assert response.status_code == 200
            assert PRIVATE not in response.text
            assert response.json()["result"] == {"page_count": 2}
            assert "processing failed" in response.json()["errorMessage"].lower()
    finally:
        get_settings.cache_clear()
