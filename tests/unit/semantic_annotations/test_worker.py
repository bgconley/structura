from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID, uuid4

from lib.semantic_annotations.models import QualityMode
from workers.semantic_annotations.worker import process_next_semantic_annotation_job


def test_semantic_annotation_worker_processes_semantic_annotate_job() -> None:
    document_id = uuid4()
    household_id = uuid4()
    job_id = uuid4()
    annotation_id = uuid4()
    queued_job_id = uuid4()
    job_service = RecordingJobService(
        SimpleNamespace(
            state=SimpleNamespace(job_id=job_id, job_type="semantic_annotate"),
            document_id=document_id,
            household_id=household_id,
            payload={
                "quality_mode": "high_quality",
                "requested_by": "reviewer",
                "allow_8b_rescue": True,
                "requested_by_user_id": str(uuid4()),
                "user_intent_reason": "User allowed one 8B rescue.",
            },
        )
    )
    service = RecordingSemanticService(
        annotation_id=annotation_id,
        queued_granite_job_ids=(queued_job_id,),
    )

    processed = process_next_semantic_annotation_job(
        worker_name="worker-semantic-annotations-test",
        job_service=job_service,
        service=service,
    )

    assert processed is True
    assert service.calls == [
        {
            "document_id": document_id,
            "quality_mode": "high_quality",
            "requested_by": "reviewer",
            "allow_8b_rescue": True,
            "requested_by_user_id": UUID(job_service.claimed.payload["requested_by_user_id"]),
            "user_intent_reason": "User allowed one 8B rescue.",
        }
    ]
    assert job_service.completed == [
        {
            "job_id": job_id,
            "result": {
                "semantic_annotation_status": "succeeded",
                "annotation_id": str(annotation_id),
                "queued_granite_job_ids": [str(queued_job_id)],
            },
        }
    ]
    assert job_service.failed == []


def test_semantic_annotation_worker_fails_unknown_job_type() -> None:
    job_id = uuid4()
    job_service = RecordingJobService(
        SimpleNamespace(
            state=SimpleNamespace(job_id=job_id, job_type="not_supported"),
            document_id=uuid4(),
            household_id=uuid4(),
            payload={},
        )
    )

    processed = process_next_semantic_annotation_job(
        worker_name="worker-semantic-annotations-test",
        job_service=job_service,
        service=RecordingSemanticService(annotation_id=uuid4(), queued_granite_job_ids=()),
    )

    assert processed is True
    assert job_service.completed == []
    assert job_service.failed[0]["job_id"] == job_id
    assert job_service.failed[0]["retryable"] is False


class RecordingJobService:
    def __init__(self, claimed: object | None) -> None:
        self.claimed = claimed
        self.completed: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []

    def claim_next_job_record(self, **_kwargs: object) -> object | None:
        return self.claimed

    def complete_job(self, **kwargs: object) -> None:
        self.completed.append(kwargs)

    def fail_job(self, **kwargs: object) -> None:
        self.failed.append(kwargs)


class RecordingSemanticService:
    def __init__(
        self,
        *,
        annotation_id: UUID,
        queued_granite_job_ids: tuple[UUID, ...],
    ) -> None:
        self.annotation_id = annotation_id
        self.queued_granite_job_ids = queued_granite_job_ids
        self.calls: list[dict[str, object]] = []

    def annotate_document(
        self,
        document_id: UUID,
        *,
        quality_mode: QualityMode,
        requested_by: str,
        allow_8b_rescue: bool = False,
        requested_by_user_id: UUID | None = None,
        user_intent_reason: str | None = None,
    ) -> RunResult:
        self.calls.append(
            {
                "document_id": document_id,
                "quality_mode": quality_mode,
                "requested_by": requested_by,
                "allow_8b_rescue": allow_8b_rescue,
                "requested_by_user_id": requested_by_user_id,
                "user_intent_reason": user_intent_reason,
            }
        )
        return RunResult(
            annotation_id=self.annotation_id,
            queued_granite_job_ids=self.queued_granite_job_ids,
        )


@dataclass(frozen=True)
class RunResult:
    annotation_id: UUID
    queued_granite_job_ids: tuple[UUID, ...]
