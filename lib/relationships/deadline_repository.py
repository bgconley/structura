from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, TypeAlias, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.documents.access_policy import DocumentAccessContext, document_read_access_params

Row: TypeAlias = dict[str, Any]


def list_deadline_rows(
    cur: Any,
    *,
    access: DocumentAccessContext,
    document_id: UUID | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[Row]:
    cur.execute(
        """
        SELECT
          dd.id,
          dd.document_id,
          d.title AS document_title,
          dd.deadline_type::text AS deadline_type,
          dd.due_on,
          dd.remind_from,
          dd.status,
          dd.confidence,
          dd.evidence_json,
          dd.metadata_json
        FROM document_deadlines dd
        JOIN documents d ON d.id = dd.document_id
        WHERE d.household_id = %s
          AND d.deleted_at IS NULL
          AND (%s::uuid IS NULL OR dd.document_id = %s)
          AND (%s::text IS NULL OR dd.status = %s)
          AND document_is_readable(d.id, %s, %s, %s)
        ORDER BY dd.due_on ASC, d.title, dd.id
        LIMIT %s
        """,
        (
            access.household_id,
            document_id,
            document_id,
            status,
            status,
            *document_read_access_params(access),
            limit,
        ),
    )
    return cast(list[Row], cur.fetchall())


def upsert_deadline(
    cur: Any,
    *,
    document_id: UUID,
    deadline_type: str,
    due_on: date,
    confidence: float | None,
    evidence: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> UUID:
    cur.execute(
        """
        INSERT INTO document_deadlines
          (document_id, deadline_type, due_on, status, confidence, evidence_json, metadata_json)
        VALUES (%s, %s, %s, 'open', %s, %s::jsonb, %s::jsonb)
        ON CONFLICT (document_id, deadline_type, due_on)
          WHERE status IN ('open', 'due_soon', 'overdue', 'needs_review')
        DO UPDATE SET confidence = GREATEST(
                        COALESCE(document_deadlines.confidence, 0),
                        COALESCE(EXCLUDED.confidence, 0)
                      ),
                      evidence_json = EXCLUDED.evidence_json,
                      metadata_json = document_deadlines.metadata_json || EXCLUDED.metadata_json,
                      updated_at = now()
        RETURNING id
        """,
        (
            document_id,
            deadline_type,
            due_on,
            confidence,
            Jsonb(list(evidence)),
            Jsonb(dict(metadata)),
        ),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Deadline upsert failed.")
    return cast(UUID, row["id"])
