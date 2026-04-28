from __future__ import annotations

from uuid import uuid4

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


class ExistingQueuedJobCursor:
    def __init__(self, existing_job_id) -> None:
        self.existing_job_id = existing_job_id
        self.queries: list[str] = []

    def execute(self, query: str, _params: object = None) -> None:
        self.queries.append(query)

    def fetchone(self) -> dict[str, object]:
        return {"id": self.existing_job_id}
