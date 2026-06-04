from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb


def update_plan_task_visual_summary(
    cur: Any,
    *,
    plan_task_id: UUID | None,
    extraction_metadata: dict[str, Any],
) -> None:
    summary = _visual_plan_summary_from_metadata(extraction_metadata)
    if plan_task_id is None or summary is None:
        return
    cur.execute(
        """
        UPDATE semantic_extraction_plan_tasks
        SET visual_plan_summary = %s::jsonb
        WHERE id = %s
        """,
        (Jsonb(summary), plan_task_id),
    )


def _visual_plan_summary_from_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    summary: dict[str, Any] = {}
    if "visualInputPlan" in metadata:
        summary["visualInputPlan"] = metadata["visualInputPlan"]
    if "visualInputAttempts" in metadata:
        summary["visualInputAttempts"] = metadata["visualInputAttempts"]
    return summary or None
