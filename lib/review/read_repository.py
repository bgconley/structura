from __future__ import annotations

from uuid import UUID

from lib.contracts import CanonicalField, FieldCandidate, ReviewTask
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext, document_read_access_params
from lib.review.access import assert_readable
from lib.review.mappers import (
    canonical_field_from_row,
    field_candidate_from_row,
    review_task_from_row,
)


def list_review_tasks(
    *,
    access: DocumentAccessContext,
    status: str | None = None,
    limit: int = 50,
) -> list[ReviewTask]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  rt.id,
                  rt.document_id,
                  rt.task_type,
                  rt.status::text AS status,
                  rt.priority,
                  rt.reason,
                  rt.metadata_json
                FROM review_tasks rt
                JOIN documents d ON d.id = rt.document_id
                WHERE document_is_readable(d.id, %s, %s, %s)
                  AND (%s::text IS NULL OR rt.status::text = %s)
                ORDER BY rt.priority DESC, rt.created_at ASC
                LIMIT %s
                """,
                (*document_read_access_params(access), status, status, limit),
            )
            rows = cur.fetchall()
    return [review_task_from_row(row) for row in rows]


def list_field_candidates(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    field_path: str | None = None,
) -> list[FieldCandidate]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_readable(cur, document_id, access)
            cur.execute(
                """
                SELECT *
                FROM field_candidates
                WHERE document_id = %s
                  AND (%s::text IS NULL OR field_path = %s)
                ORDER BY
                  field_path,
                  authority_weight DESC,
                  confidence DESC NULLS LAST,
                  created_at DESC
                """,
                (document_id, field_path, field_path),
            )
            rows = cur.fetchall()
    return [field_candidate_from_row(row) for row in rows]


def list_canonical_fields(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
) -> list[CanonicalField]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_readable(cur, document_id, access)
            cur.execute(
                """
                SELECT *
                FROM canonical_fields
                WHERE document_id = %s
                ORDER BY field_path, ordinal
                """,
                (document_id,),
            )
            rows = cur.fetchall()
    return [canonical_field_from_row(row) for row in rows]
