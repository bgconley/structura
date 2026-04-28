from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from workers.docling import worker


def test_docling_worker_does_not_fail_completed_parse_when_downstream_enqueue_fails(
    monkeypatch,
) -> None:
    document_id = uuid4()
    household_id = uuid4()
    job_id = uuid4()
    job_service = RecordingJobService(
        claimed=SimpleNamespace(
            document_id=document_id,
            household_id=household_id,
            payload={"document_id": str(document_id)},
            state=SimpleNamespace(job_id=job_id),
        )
    )

    monkeypatch.setattr(worker, "JobService", lambda: job_service)
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

    assert job_service.completed == [job_id]
    assert job_service.failed == []
    assert parse_failures == []


class RecordingJobService:
    def __init__(self, *, claimed: object) -> None:
        self.claimed = claimed
        self.completed: list[object] = []
        self.failed: list[object] = []
        self.created: list[dict[str, object]] = []

    def claim_next_job_record(self, **_kwargs: object) -> object:
        return self.claimed

    def complete_job(self, *, job_id: object, result: object) -> None:
        del result
        self.completed.append(job_id)

    def fail_job(self, *, job_id: object, **_kwargs: object) -> None:
        self.failed.append(job_id)

    def create_job(self, **kwargs: object) -> SimpleNamespace:
        self.created.append(kwargs)
        return SimpleNamespace(job_id=uuid4())
