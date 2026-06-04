from __future__ import annotations

import json
from typing import Any, cast
from uuid import uuid4

from lib.extraction.extraction_plan_task_repository import update_plan_task_visual_summary


def test_plan_task_visual_summary_update_persists_decision_and_attempts() -> None:
    cursor = RecordingCursor()
    plan_task_id = uuid4()

    update_plan_task_visual_summary(
        cursor,
        plan_task_id=plan_task_id,
        extraction_metadata={
            "visualInputPlan": {
                "mode": "planned",
                "scope": "full_page",
                "fallbackReason": "low_resolution_page_requires_full_page",
            },
            "visualInputAttempts": [
                {
                    "useful": False,
                    "failureReason": "crop_output_not_useful",
                    "visualInputPlan": {"scope": "expanded_crop"},
                },
                {
                    "useful": True,
                    "visualInputPlan": {"scope": "full_page_retry"},
                },
            ],
        },
    )

    sql, params = cursor.calls[0]
    assert "UPDATE semantic_extraction_plan_tasks" in sql
    assert "visual_plan_summary = %s::jsonb" in sql
    assert params[1] == plan_task_id
    summary = json.loads(json.dumps(cast(Any, params[0]).obj))
    assert summary == {
        "visualInputPlan": {
            "mode": "planned",
            "scope": "full_page",
            "fallbackReason": "low_resolution_page_requires_full_page",
        },
        "visualInputAttempts": [
            {
                "useful": False,
                "failureReason": "crop_output_not_useful",
                "visualInputPlan": {"scope": "expanded_crop"},
            },
            {
                "useful": True,
                "visualInputPlan": {"scope": "full_page_retry"},
            },
        ],
    }


def test_plan_task_visual_summary_update_skips_without_plan_task_or_visual_metadata() -> None:
    cursor = RecordingCursor()

    update_plan_task_visual_summary(
        cursor,
        plan_task_id=None,
        extraction_metadata={"visualInputPlan": {"scope": "full_page"}},
    )
    update_plan_task_visual_summary(
        cursor,
        plan_task_id=uuid4(),
        extraction_metadata={"unrelated": "metadata"},
    )

    assert cursor.calls == []


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))
