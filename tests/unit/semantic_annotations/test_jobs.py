from __future__ import annotations

from uuid import uuid4

import pytest

from lib.semantic_annotations import jobs as semantic_jobs


def test_semantic_annotation_enqueue_rejects_removed_high_quality_mode() -> None:
    with pytest.raises(ValueError, match="removed"):
        semantic_jobs.enqueue_semantic_annotation_job(
            NoExistingJobCursor(),
            document_id=uuid4(),
            household_id=uuid4(),
            quality_mode="high_quality",
            semantic_quality_mode="high_quality",
            requested_by="user",
        )


def test_rescue_semantic_enqueue_rejects_removed_rescue_mode() -> None:
    with pytest.raises(ValueError, match="removed"):
        semantic_jobs.enqueue_semantic_annotation_job(
            NoExistingJobCursor(),
            document_id=uuid4(),
            household_id=uuid4(),
            quality_mode="rescue",
            semantic_quality_mode="smart",
            allow_8b_rescue=True,
            requested_by="user",
            source_semantic_region_id=uuid4(),
            rescue_failure_class="missing_required_field",
        )


def test_rescue_semantic_enqueue_requires_persisted_user_permission() -> None:
    with pytest.raises(ValueError, match="removed"):
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
    with pytest.raises(ValueError, match="removed"):
        semantic_jobs.enqueue_semantic_annotation_job(
            NoExistingJobCursor(),
            document_id=uuid4(),
            household_id=uuid4(),
            quality_mode="high_quality",
            semantic_quality_mode="high_quality",
            requested_by="system",
        )


class NoExistingJobCursor:
    def execute(self, _query: str, _params: object = None) -> None:
        return None

    def fetchone(self) -> None:
        return None
