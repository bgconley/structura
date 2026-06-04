from __future__ import annotations

from typing import Any

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
from lib.jobs.failure_taxonomy import failure_taxonomy_code
from lib.jobs.service import _candidate_cancel_job_ids, _recover_expired_running_jobs


class RecordingCursor:
    def __init__(self) -> None:
        self.rowcount = 0
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.rows: list[dict[str, Any]] = []

    def execute(self, sql: Any, params: tuple[Any, ...] | list[Any]) -> None:
        self.calls.append((sql, params))

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


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


def test_job_failure_taxonomy_preserves_explicit_failure_codes() -> None:
    assert (
        failure_taxonomy_code(
            queue_name="extraction",
            job_type="extract",
            error_class="ModelTimeoutError",
            details={"taxonomy_code": "granite_timeout"},
        )
        == "granite_timeout"
    )
    assert (
        failure_taxonomy_code(
            queue_name="semantic-annotations",
            job_type="semantic_annotate",
            error_class="ModelProtocolError",
            details={"failureCode": "semantic_model_protocol_error"},
        )
        == "semantic_model_protocol_error"
    )


def test_job_failure_taxonomy_derives_stable_codes_from_queue_and_error_class() -> None:
    assert (
        failure_taxonomy_code(
            queue_name="extraction",
            job_type="extract",
            error_class="ModelTimeoutError",
            details=None,
        )
        == "extraction_model_timeout"
    )
    assert (
        failure_taxonomy_code(
            queue_name="visual-embeddings",
            job_type="embed_visual",
            error_class="WorkerLeaseExpired",
            details=None,
        )
        == "visual_embeddings_worker_lease_expired"
    )
    assert (
        failure_taxonomy_code(
            queue_name="custom-maintenance",
            job_type="nightly_cleanup",
            error_class="RuntimeError",
            details=None,
        )
        == "custom_maintenance_runtime_error"
    )


def test_expired_worker_lease_recovery_records_taxonomy_code() -> None:
    cursor = RecordingCursor()

    recovered = _recover_expired_running_jobs(
        cursor,
        queue_name="visual-embeddings",
        document_id=None,
    )

    assert recovered == 0
    assert cursor.calls
    sql, params = cursor.calls[0]
    assert "'taxonomy_code'" in sql
    assert params[0] == "visual_embeddings_worker_lease_expired"


def test_candidate_cancel_query_keeps_title_prefix_parameterized() -> None:
    cursor = RecordingCursor()
    cursor.rows = [{"id": "job-1"}]
    title_prefix = "unsafe%' OR true --"

    candidates = _candidate_cancel_job_ids(
        cursor,
        household_id=None,
        job_ids=(),
        document_ids=(),
        queue_names=(),
        statuses=("queued",),
        title_prefix=title_prefix,
        max_jobs=10,
    )

    assert candidates == ["job-1"]
    sql, params = cursor.calls[0]
    assert isinstance(sql, str)
    assert title_prefix not in sql
    assert params == [
        ["queued"],
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        f"{title_prefix}%",
        f"{title_prefix}%",
        10,
    ]
