from __future__ import annotations

from uuid import UUID

from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.review.access import assert_writable
from lib.review.audit_repository import (
    close_field_review_tasks,
    record_review_event,
    update_document_review_status,
)


def record_reclassify(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    family: str,
    subtype: str | None,
    reason: str | None,
) -> UUID:
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_writable(cur, document_id, access)
            cur.execute(
                """
                SELECT document_family::text AS family, document_subtype
                FROM documents
                WHERE id = %s
                FOR UPDATE
                """,
                (document_id,),
            )
            previous = cur.fetchone()
            cur.execute(
                """
                UPDATE documents
                SET document_family = %s,
                    document_subtype = %s,
                    review_status = 'user_corrected',
                    updated_at = now()
                WHERE id = %s
                """,
                (family, subtype, document_id),
            )
            event_id = record_review_event(
                cur,
                document_id=document_id,
                review_task_id=None,
                field_path="classification.document_family",
                action="reclassify_document",
                old_value=previous,
                new_value={"family": family, "subtype": subtype},
                actor_label=str(actor_user_id),
                reason=reason,
            )
            close_field_review_tasks(cur, document_id, "classification.document_family")
            update_document_review_status(cur, document_id)
        conn.commit()
    return event_id


def mark_done(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    review_task_id: UUID | None,
    reason: str | None,
) -> UUID:
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_writable(cur, document_id, access)
            if review_task_id:
                cur.execute(
                    """
                    UPDATE review_tasks
                    SET status = 'resolved',
                        updated_at = now()
                    WHERE id = %s
                      AND document_id = %s
                    """,
                    (review_task_id, document_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE review_tasks
                    SET status = 'resolved',
                        updated_at = now()
                    WHERE document_id = %s
                      AND status IN ('open', 'in_progress')
                    """,
                    (document_id,),
                )
            event_id = record_review_event(
                cur,
                document_id=document_id,
                review_task_id=review_task_id,
                field_path=None,
                action="mark_done",
                old_value=None,
                new_value={"status": "resolved"},
                actor_label=str(actor_user_id),
                reason=reason,
            )
            update_document_review_status(cur, document_id)
        conn.commit()
    return event_id


def record_rerun_request(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    target_schema_name: str | None,
    reason: str | None,
) -> UUID:
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_writable(cur, document_id, access)
            event_id = record_review_event(
                cur,
                document_id=document_id,
                review_task_id=None,
                field_path=None,
                action="rerun_extraction",
                old_value=None,
                new_value={
                    "job_type": "semantic_annotate",
                    "quality_mode": "smart",
                    "requested_target_schema_name": target_schema_name,
                },
                actor_label=str(actor_user_id),
                reason=reason,
            )
        conn.commit()
    return event_id
