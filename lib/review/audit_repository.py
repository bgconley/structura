from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.review.errors import ReviewRepositoryError


def record_review_event(
    cur: Any,
    *,
    document_id: UUID,
    review_task_id: UUID | None,
    field_path: str | None,
    action: str,
    old_value: object,
    new_value: object,
    actor_label: str,
    reason: str | None,
) -> UUID:
    cur.execute(
        """
        INSERT INTO review_events
          (
            review_task_id, document_id, field_path, action, old_value_json,
            new_value_json, reason, actor_label
          )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        RETURNING id
        """,
        (
            review_task_id,
            document_id,
            field_path,
            action,
            Jsonb(old_value),
            Jsonb(new_value),
            reason,
            actor_label,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ReviewRepositoryError("Review event insert failed.")
    return cast(UUID, row["id"])


def record_history(
    cur: Any,
    *,
    document_id: UUID,
    canonical_field_id: UUID,
    field_path: str,
    action: str,
    old_value: object,
    new_value: object,
    actor_user_id: UUID,
    reason: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO canonical_fact_history
          (
            document_id, canonical_field_id, field_path, action, old_value_json,
            new_value_json, actor_user_id, reason
          )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        """,
        (
            document_id,
            canonical_field_id,
            field_path,
            action,
            Jsonb(old_value),
            Jsonb(new_value),
            actor_user_id,
            reason,
        ),
    )


def close_field_review_tasks(
    cur: Any, document_id: UUID, field_path: str, *, ordinal: int | None = None
) -> None:
    cur.execute(
        """
        UPDATE review_tasks rt
        SET status = 'resolved',
            updated_at = now()
        WHERE document_id = %s
          AND status IN ('open', 'in_progress')
          AND COALESCE(metadata_json->>'fieldPath', '') = %s
          AND (
            %s::integer IS NULL OR
            CASE
              WHEN metadata_json ? 'candidateId' THEN (
                SELECT fc.ordinal::text FROM field_candidates fc
                WHERE fc.id::text = rt.metadata_json->>'candidateId'
                  AND fc.document_id = rt.document_id
                  AND fc.field_path = rt.metadata_json->>'fieldPath'
                  AND (
                    NOT (rt.metadata_json ? 'ordinal')
                    OR fc.ordinal::text = rt.metadata_json->>'ordinal'
                  )
              )
              WHEN metadata_json ? 'ordinal' THEN metadata_json->>'ordinal'
              ELSE '1'
            END = %s::text
          )
        """,
        (document_id, field_path, ordinal, str(ordinal) if ordinal is not None else None),
    )


def update_document_review_status(cur: Any, document_id: UUID) -> None:
    cur.execute(
        """
        UPDATE documents
        SET review_status = CASE
          WHEN EXISTS (
            SELECT 1 FROM review_tasks
            WHERE document_id = %s AND status IN ('open', 'in_progress')
          ) THEN 'needs_review'::review_status_enum
          ELSE 'user_confirmed'::review_status_enum
        END,
        updated_at = now()
        WHERE id = %s
        """,
        (document_id, document_id),
    )
