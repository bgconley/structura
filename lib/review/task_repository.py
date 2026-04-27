from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb


def upsert_review_task(
    cur: Any,
    *,
    document_id: UUID,
    extraction_id: UUID | None,
    task_type: str,
    reason: str,
    priority: int,
    metadata: Mapping[str, Any],
) -> None:
    field_path = metadata.get("fieldPath")
    page_number = metadata.get("pageNumber")
    cur.execute(
        """
        SELECT id
        FROM review_tasks
        WHERE document_id = %s
          AND task_type = %s
          AND status IN ('open', 'in_progress')
          AND COALESCE(metadata_json->>'fieldPath', '') = COALESCE(%s, '')
          AND COALESCE(metadata_json->>'pageNumber', '') = COALESCE(%s, '')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (
            document_id,
            task_type,
            str(field_path) if field_path else None,
            str(page_number) if page_number else None,
        ),
    )
    existing = cur.fetchone()
    if existing:
        cur.execute(
            """
            UPDATE review_tasks
            SET extraction_id = %s,
                reason = %s,
                priority = GREATEST(priority, %s),
                metadata_json = metadata_json || %s::jsonb,
                updated_at = now()
            WHERE id = %s
            """,
            (extraction_id, reason, priority, Jsonb(dict(metadata)), existing["id"]),
        )
        return
    cur.execute(
        """
        INSERT INTO review_tasks
          (document_id, extraction_id, task_type, reason, priority, metadata_json)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (document_id, extraction_id, task_type, reason, priority, Jsonb(dict(metadata))),
    )
