from __future__ import annotations

from uuid import uuid4

import pytest

from lib.semantic_annotations import jobs as semantic_jobs


def test_semantic_annotation_enqueue_can_dedupe_existing_queued_high_quality_job(
    monkeypatch,
) -> None:
    document_id = uuid4()
    household_id = uuid4()
    existing_job_id = uuid4()
    cur = ExistingQueuedJobCursor(existing_job_id)

    def fail_create(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("duplicate high-quality job should not be created")

    monkeypatch.setattr(semantic_jobs, "create_job_with_cursor", fail_create)

    returned = semantic_jobs.enqueue_semantic_annotation_job(
        cur,
        document_id=document_id,
        household_id=household_id,
        quality_mode="high_quality",
        requested_by="user",
        dedupe_existing=True,
    )

    assert returned == existing_job_id
    assert any("status IN ('queued', 'running')" in query for query in cur.queries)


def test_rescue_semantic_enqueue_requires_persisted_user_permission() -> None:
    with pytest.raises(ValueError, match="8B rescue"):
        semantic_jobs.enqueue_semantic_annotation_job(
            NoExistingJobCursor(),
            document_id=uuid4(),
            household_id=uuid4(),
            quality_mode="rescue",
            semantic_quality_mode="smart",
            allow_8b_rescue=False,
            requested_by="user",
            source_semantic_region_id=uuid4(),
            rescue_failure_class="missing_required_field",
        )


def test_high_quality_semantic_enqueue_requires_explicit_user_or_agent_intent() -> None:
    with pytest.raises(ValueError, match="high-quality"):
        semantic_jobs.enqueue_semantic_annotation_job(
            NoExistingJobCursor(),
            document_id=uuid4(),
            household_id=uuid4(),
            quality_mode="high_quality",
            semantic_quality_mode="high_quality",
            requested_by="system",
        )


def test_rescue_semantic_enqueue_dedupes_region_failure_class(monkeypatch) -> None:
    document_id = uuid4()
    household_id = uuid4()
    region_id = uuid4()
    existing_job_id = uuid4()
    cur = ExistingRescueJobCursor(existing_job_id)

    def fail_create(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("duplicate rescue job should not be created")

    monkeypatch.setattr(semantic_jobs, "create_job_with_cursor", fail_create)

    returned = semantic_jobs.enqueue_semantic_annotation_job(
        cur,
        document_id=document_id,
        household_id=household_id,
        quality_mode="rescue",
        semantic_quality_mode="smart",
        allow_8b_rescue=True,
        source_semantic_region_id=region_id,
        rescue_failure_class="missing_required_field",
        requested_by="user",
        requested_by_user_id=uuid4(),
        user_intent_reason="User allowed one rescue.",
        dedupe_existing=True,
    )

    assert returned == existing_job_id
    assert any("source_semantic_region_id" in query for query in cur.queries)
    assert any("failure_class" in query for query in cur.queries)


class ExistingQueuedJobCursor:
    def __init__(self, existing_job_id) -> None:
        self.existing_job_id = existing_job_id
        self.queries: list[str] = []

    def execute(self, query: str, _params: object = None) -> None:
        self.queries.append(query)

    def fetchone(self) -> dict[str, object]:
        return {"id": self.existing_job_id}


class ExistingRescueJobCursor(ExistingQueuedJobCursor):
    pass


class NoExistingJobCursor:
    def execute(self, _query: str, _params: object = None) -> None:
        return None

    def fetchone(self) -> None:
        return None
