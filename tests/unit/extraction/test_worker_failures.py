from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

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


def test_extraction_worker_does_not_retry_granite_model_timeout(monkeypatch) -> None:
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
    assert job_service.failed[0]["retryable"] is False
    assert job_service.failed[0]["details"]["model_failure_policy"] == "do_not_retry_timeout"


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
    assert job_service.failed[0]["details"]["model_runtime_details"] == {
        "finish_reason": "length",
        "usage": {"completion_tokens": 1024},
    }


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
