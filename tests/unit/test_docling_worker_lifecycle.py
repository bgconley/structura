from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from workers.docling import worker


def _claimed_job(document_id, household_id, job_id):
    return SimpleNamespace(
        claim_token=uuid4(),
        attempt_count=1,
        max_attempts=5,
        document_id=document_id,
        household_id=household_id,
        payload={"document_id": str(document_id)},
        state=SimpleNamespace(job_id=job_id),
    )


def _stub_successful_parse(monkeypatch) -> None:
    monkeypatch.setattr(
        worker,
        "convert_document",
        lambda *_args, **_kwargs: SimpleNamespace(
            docling_asset_id=uuid4(),
            page_count=1,
            element_count=2,
            table_count=0,
            chunk_count=1,
        ),
    )
    monkeypatch.setattr(
        worker,
        "evaluate_document_quality",
        lambda *_args, **_kwargs: SimpleNamespace(
            review_required=False,
            visual_embedding_eligible=False,
            qwen_route_eligible=False,
        ),
    )


def test_docling_worker_fails_job_retryably_when_semantic_enqueue_fails(monkeypatch) -> None:
    document_id = uuid4()
    job_id = uuid4()
    job_service = RecordingJobService(
        claimed=_claimed_job(document_id, uuid4(), job_id),
    )

    monkeypatch.setattr(worker, "JobService", lambda: job_service)
    _stub_successful_parse(monkeypatch)
    monkeypatch.setattr(worker, "_enqueue_embedding_refresh", lambda *_args, **_kwargs: None)

    def fail_semantic_enqueue(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("semantic queue unavailable")

    parse_failures: list[dict[str, object]] = []
    monkeypatch.setattr(worker, "_enqueue_semantic_annotation", fail_semantic_enqueue)
    monkeypatch.setattr(
        worker,
        "mark_document_parse_failed",
        lambda **kwargs: parse_failures.append(kwargs),
    )

    assert worker.process_next_docling_job(worker_name="worker-test", queue_name="docling")

    assert job_service.completed == []
    assert len(job_service.failed) == 1
    failure = job_service.failed[0]
    assert failure["job_id"] == job_id
    assert failure["error_class"] == "RuntimeError"
    assert failure["retryable"] is True
    assert "semantic annotation enqueue failed" in str(failure["message"])
    # The parse itself succeeded; only the job retries, the document is not
    # marked parse-failed.
    assert parse_failures == []


def test_docling_worker_completes_job_and_records_degraded_health_for_embedding_failure(
    monkeypatch,
) -> None:
    document_id = uuid4()
    job_id = uuid4()
    semantic_job_id = uuid4()
    job_service = RecordingJobService(
        claimed=_claimed_job(document_id, uuid4(), job_id),
    )

    monkeypatch.setattr(worker, "JobService", lambda: job_service)
    _stub_successful_parse(monkeypatch)
    monkeypatch.setattr(
        worker,
        "_enqueue_semantic_annotation",
        lambda *_args, **_kwargs: semantic_job_id,
    )

    def fail_embedding_enqueue(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("embedding queue unavailable")

    health_records: list[dict[str, object]] = []
    monkeypatch.setattr(worker, "_enqueue_embedding_refresh", fail_embedding_enqueue)
    monkeypatch.setattr(
        worker,
        "record_service_health",
        lambda **kwargs: health_records.append(kwargs),
    )

    assert worker.process_next_docling_job(worker_name="worker-test", queue_name="docling")

    assert job_service.completed == [job_id]
    assert job_service.failed == []
    assert job_service.results[0]["queued_semantic_annotation_job_id"] == str(semantic_job_id)
    assert health_records[0]["status"] == "degraded"
    metrics = health_records[0]["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["failures"] == ["embeddings:RuntimeError"]


def test_docling_worker_does_not_mark_parse_failed_after_ownership_loss(monkeypatch) -> None:
    from lib.jobs.errors import JobOwnershipLost

    jobs = RecordingJobService(claimed=_claimed_job(uuid4(), uuid4(), uuid4()))
    monkeypatch.setattr(worker, "JobService", lambda: jobs)

    def stale_publication(*_args, **_kwargs):
        raise JobOwnershipLost("stale")

    failures = []
    monkeypatch.setattr(worker, "convert_document", stale_publication)
    monkeypatch.setattr(worker, "mark_document_parse_failed", lambda **kw: failures.append(kw))
    assert worker.process_next_docling_job(worker_name="worker-test", queue_name="docling")
    assert failures == []
    assert jobs.failed == []
    assert jobs.completed == []


class RecordingJobService:
    def __init__(self, *, claimed: object, complete_status: str = "succeeded") -> None:
        self.claimed = claimed
        self.complete_status = complete_status
        self.completed: list[object] = []
        self.results: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []
        self.cancelled: list[dict[str, object]] = []
        self.created: list[dict[str, object]] = []

    def claim_next_job_record(self, **_kwargs: object) -> object:
        return self.claimed

    def complete_job(
        self, *, job_id: object, claim_token: object, result: dict[str, object]
    ) -> SimpleNamespace:
        self.completed.append(job_id)
        self.results.append(result)
        return SimpleNamespace(status=self.complete_status)

    def fail_job(self, *, job_id: object, **kwargs: object) -> None:
        self.failed.append({"job_id": job_id, **kwargs})

    def cancel_job(self, **kwargs: object) -> None:
        self.cancelled.append(kwargs)

    def create_job(self, **kwargs: object) -> SimpleNamespace:
        self.created.append(kwargs)
        return SimpleNamespace(job_id=uuid4())
