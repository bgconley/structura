from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.review.access import assert_writable
from lib.review.audit_repository import (
    close_field_review_tasks,
    record_review_event,
    update_document_review_status,
)
from lib.review.errors import ReviewRepositoryError
from lib.review.line_items.errors import LineDecisionConflict

# Observation acceptance remains candidate review; canonical lines use the explicit
# versioned endpoint and retained source/slot authority.
_DECISION_STATUS = {"accept": "accepted", "reject": "rejected"}


def decide_observation(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    observation_id: UUID,
    decision: str,
    reason: str | None,
) -> UUID:
    status = _decision_status(decision)
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_writable(cur, document_id, access)
            cur.execute(
                """
                UPDATE extraction_observations
                SET status = %s,
                    updated_at = now()
                WHERE id = %s
                  AND document_id = %s
                RETURNING observation_family, field_name, value_json, status
                """,
                (status, observation_id, document_id),
            )
            row = cur.fetchone()
            if not row:
                raise ReviewRepositoryError("Observation candidate not found.")
            field_path = _observation_field_path(row)
            event_id = record_review_event(
                cur,
                document_id=document_id,
                review_task_id=None,
                field_path=field_path,
                action=f"{decision}_observation",
                old_value={"observationId": str(observation_id)},
                new_value={"status": status, "value": row.get("value_json")},
                actor_label=str(actor_user_id),
                reason=reason,
            )
            close_field_review_tasks(cur, document_id, field_path)
            update_document_review_status(cur, document_id)
        conn.commit()
    return event_id


def decide_line_item(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    candidate_id: UUID,
    decision: str,
    reason: str | None,
) -> UUID:
    # This signature stays import-compatible but cannot bypass source/slot revisions.
    raise LineDecisionConflict()


def _decision_status(decision: str) -> str:
    status = _DECISION_STATUS.get(decision)
    if status is None:
        raise ReviewRepositoryError(f"Unsupported candidate decision: {decision}")
    return status


def _observation_field_path(row: dict[str, Any]) -> str:
    family = str(row.get("observation_family") or "document_observation")
    field_name = str(row.get("field_name") or "observation")
    return f"observations.{family}.{field_name}"
