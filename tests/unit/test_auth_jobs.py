from __future__ import annotations

import pytest

from lib.auth import hash_secret
from lib.auth.service import hash_password, verify_password
from lib.jobs import (
    JobServiceError,
    PayloadSafetyError,
    queue_transport_profile,
    retry_delay_seconds,
    sanitize_job_payload,
)


def test_argon2id_password_hash_verifies_and_rejects_wrong_password() -> None:
    password_hash = hash_password("minimum8")

    assert "argon2id" in password_hash
    assert verify_password(password_hash, "minimum8")
    assert not verify_password(password_hash, "wrong-password")


def test_session_secret_hash_is_stable_without_storing_raw_secret() -> None:
    assert hash_secret("token") == hash_secret("token")
    assert hash_secret("token") != "token"


def test_job_payload_safety_rejects_raw_document_text_and_prompt_content() -> None:
    with pytest.raises(PayloadSafetyError):
        sanitize_job_payload({"document_id": "abc", "raw_document_text": "sensitive"})
    with pytest.raises(PayloadSafetyError):
        sanitize_job_payload({"nested": {"prompt_body": "classify this whole document"}})


def test_job_payload_safety_allows_small_references() -> None:
    payload = sanitize_job_payload(
        {
            "job_id": "job",
            "document_id": "doc",
            "stage": "document.preview",
            "priority": 5,
            "trace_id": "trace",
        }
    )

    assert payload["stage"] == "document.preview"


def test_retry_delay_uses_bounded_exponential_backoff() -> None:
    assert retry_delay_seconds(1) == 30
    assert retry_delay_seconds(2) == 60
    assert retry_delay_seconds(8) == 3600


def test_queue_transport_profile_documents_phase0_fallback() -> None:
    pgmq = queue_transport_profile("pgmq")

    assert pgmq.requested == "pgmq"
    assert pgmq.active == "pipeline_jobs"
    assert pgmq.reason
    assert queue_transport_profile("pipeline_jobs").active == "pipeline_jobs"
    with pytest.raises(JobServiceError):
        queue_transport_profile("unknown")
