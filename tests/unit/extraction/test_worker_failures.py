from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from lib.model_runtime.http_client import ModelProtocolError, ModelTimeoutError
from workers import extraction as extraction_worker_module
from workers.extraction.worker import process_next_extraction_job


def test_extraction_worker_records_exception_details_for_failed_extract(monkeypatch) -> None:
    document_id = uuid4()
    job_id = uuid4()
    job_service = RecordingJobService(
        SimpleNamespace(
            state=SimpleNamespace(job_id=job_id, job_type="extract"),
            document_id=document_id,
            household_id=uuid4(),
            payload={
                "target_schema_name": "receipt",
                "route_profile": "docling_plus_granite_structured",
            },
        )
    )
    monkeypatch.setattr(extraction_worker_module.worker, "JobService", lambda: job_service)

    processed = process_next_extraction_job(
        worker_name="worker-extraction-test",
        service=FailingExtractionService(),
    )

    assert processed is True
    assert job_service.failed[0]["job_id"] == job_id
    assert job_service.failed[0]["error_class"] == "AttributeError"
    assert job_service.failed[0]["message"] == "Extraction job failed: missing line_items"
    assert job_service.failed[0]["details"]["exception_class"] == "AttributeError"
    assert job_service.failed[0]["details"]["exception_message"] == "missing line_items"
    assert "extract_document" in job_service.failed[0]["details"]["traceback"]


@pytest.mark.parametrize(
    "route_profile",
    ["docling_plus_granite_structured", "docling_plus_structured_extraction"],
)
def test_extraction_worker_retries_granite_model_timeout_on_all_routes(
    monkeypatch,
    route_profile: str,
) -> None:
    document_id = uuid4()
    job_id = uuid4()
    job_service = RecordingJobService(
        SimpleNamespace(
            state=SimpleNamespace(job_id=job_id, job_type="extract"),
            document_id=document_id,
            household_id=uuid4(),
            payload={
                "target_schema_name": "receipt",
                "route_profile": route_profile,
                "semantic_type": "receipt_line_item_table",
                "semantic_granite_task": "tables_json",
            },
        )
    )
    monkeypatch.setattr(extraction_worker_module.worker, "JobService", lambda: job_service)

    processed = process_next_extraction_job(
        worker_name="worker-extraction-test",
        service=TimeoutExtractionService(),
    )

    assert processed is True
    assert job_service.failed[0]["error_class"] == "ModelTimeoutError"
    assert job_service.failed[0]["retryable"] is True
    assert job_service.failed[0]["details"]["model_failure_policy"] == "retryable_model_exception"


def test_extraction_worker_records_model_runtime_error_details(monkeypatch) -> None:
    document_id = uuid4()
    job_id = uuid4()
    job_service = RecordingJobService(
        SimpleNamespace(
            state=SimpleNamespace(job_id=job_id, job_type="extract"),
            document_id=document_id,
            household_id=uuid4(),
            payload={
                "target_schema_name": "receipt",
                "route_profile": "docling_plus_granite_structured",
            },
        )
    )
    monkeypatch.setattr(extraction_worker_module.worker, "JobService", lambda: job_service)

    processed = process_next_extraction_job(
        worker_name="worker-extraction-test",
        service=ProtocolExtractionService(),
    )

    assert processed is True
    assert job_service.failed[0]["error_class"] == "ModelProtocolError"
    assert job_service.failed[0]["retryable"] is False
    assert job_service.failed[0]["details"]["model_failure_policy"] == (
        "non_retryable_model_exception"
    )
    assert job_service.failed[0]["details"]["model_runtime_details"] == {
        "finish_reason": "length",
        "usage": {"completion_tokens": 1024},
    }


def test_extraction_worker_rejects_removed_rescue_payload_nonretryably(monkeypatch) -> None:
    document_id = uuid4()
    job_id = uuid4()
    job_service = RecordingJobService(
        SimpleNamespace(
            state=SimpleNamespace(job_id=job_id, job_type="extract"),
            document_id=document_id,
            household_id=uuid4(),
            payload={
                "target_schema_name": "invoice",
                "route_profile": "docling_plus_granite_structured",
                "allow_8b_rescue": True,
            },
        )
    )
    service = CapturingExtractionService()
    monkeypatch.setattr(extraction_worker_module.worker, "JobService", lambda: job_service)

    processed = process_next_extraction_job(
        worker_name="worker-extraction-test",
        service=service,
    )

    assert processed is True
    assert service.kwargs == {}
    assert job_service.failed[0]["job_id"] == job_id
    assert job_service.failed[0]["error_class"] == "ExtractionWorkerError"
    assert job_service.failed[0]["message"] == (
        "Extraction job failed: Removed semantic rescue controls are not accepted."
    )
    assert job_service.failed[0]["retryable"] is False
    assert job_service.failed[0]["details"] == {
        "model_failure_policy": "removed_semantic_rescue_control"
    }


def test_extraction_worker_passes_phase85_run_id_from_job_metadata(monkeypatch) -> None:
    document_id = uuid4()
    job_id = uuid4()
    job_service = SuccessfulJobService(
        SimpleNamespace(
            state=SimpleNamespace(job_id=job_id, job_type="extract"),
            document_id=document_id,
            household_id=uuid4(),
            payload={
                "target_schema_name": "invoice",
                "route_profile": "docling_plus_granite_structured",
                "metadata": {"run_id": "phase85-20260604-smoke-001"},
            },
        )
    )
    service = CapturingExtractionService()
    monkeypatch.setattr(extraction_worker_module.worker, "JobService", lambda: job_service)
    monkeypatch.setattr(
        extraction_worker_module.worker,
        "maybe_reconcile_semantic_annotation",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        extraction_worker_module.worker,
        "_enqueue_embedding_refresh",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        extraction_worker_module.worker,
        "_enqueue_relationship_refresh",
        lambda *_args, **_kwargs: None,
    )

    processed = process_next_extraction_job(
        worker_name="worker-extraction-test",
        service=service,
    )

    assert processed is True
    assert service.kwargs["run_id"] == "phase85-20260604-smoke-001"
    assert job_service.completed[0]["result"]["extraction_status"] == "succeeded"


def test_extraction_failure_policy_follows_model_exception_retryability_contract() -> None:
    from lib.extraction.model_failure_policy import (
        extraction_failure_policy,
        model_exception_retryable,
    )
    from lib.model_runtime.http_client import (
        ModelConfigurationError,
        ModelServiceError,
    )

    payload = {"route_profile": "docling_plus_granite_structured"}

    timeout = extraction_failure_policy(payload=payload, exc=ModelTimeoutError("timed out"))
    service = extraction_failure_policy(payload=payload, exc=ModelServiceError("HTTP 503"))
    protocol = extraction_failure_policy(payload=payload, exc=ModelProtocolError("bad JSON"))
    configuration = extraction_failure_policy(
        payload=payload,
        exc=ModelConfigurationError("bad URL"),
    )
    non_model = extraction_failure_policy(payload=payload, exc=ValueError("badly formed UUID"))

    assert timeout.retryable is True
    assert timeout.policy == "retryable_model_exception"
    assert service.retryable is True
    assert protocol.retryable is False
    assert protocol.policy == "non_retryable_model_exception"
    assert configuration.retryable is False
    assert non_model.retryable is True
    assert non_model.policy == "default_retryable"
    assert model_exception_retryable(ModelTimeoutError("timed out")) is True
    assert model_exception_retryable(ModelProtocolError("bad JSON")) is False
    assert model_exception_retryable(ValueError("not a model error")) is True


class RecordingJobService:
    def __init__(self, claimed: object | None) -> None:
        self.claimed = claimed
        self.failed: list[dict[str, object]] = []

    def claim_next_job_record(self, **_kwargs: object) -> object | None:
        return self.claimed

    def complete_job(self, **_kwargs: object) -> None:
        raise AssertionError("failed extraction jobs should not complete")

    def fail_job(self, **kwargs: object) -> None:
        self.failed.append(kwargs)


class SuccessfulJobService:
    def __init__(self, claimed: object | None) -> None:
        self.claimed = claimed
        self.completed: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []

    def claim_next_job_record(self, **_kwargs: object) -> object | None:
        return self.claimed

    def complete_job(self, **kwargs: object) -> SimpleNamespace:
        self.completed.append(kwargs)
        return SimpleNamespace(status="succeeded")

    def fail_job(self, **kwargs: object) -> None:
        self.failed.append(kwargs)


class FailingExtractionService:
    def extract_document(self, *_args: object, **_kwargs: object) -> object:
        raise AttributeError("missing line_items")


class TimeoutExtractionService:
    def extract_document(self, *_args: object, **_kwargs: object) -> object:
        raise ModelTimeoutError("Granite request timed out")


class ProtocolExtractionService:
    def extract_document(self, *_args: object, **_kwargs: object) -> object:
        raise ModelProtocolError(
            "Vision model response was truncated before valid JSON completed.",
            details={
                "finish_reason": "length",
                "usage": {"completion_tokens": 1024},
            },
        )


class CapturingExtractionService:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def extract_document(self, *_args: object, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            extraction_id=uuid4(),
            review_status="needs_review",
            candidate_count=1,
            canonical_count=0,
            review_task_count=1,
        )
