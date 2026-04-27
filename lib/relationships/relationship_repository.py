from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.documents.access_policy import DocumentAccessContext, document_read_access_params

Row: TypeAlias = dict[str, Any]


def list_relationship_rows(
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
          dr.id,
          CASE WHEN dr.from_document_id = COALESCE(%s, dr.from_document_id)
               THEN dr.from_document_id ELSE dr.to_document_id END AS document_id,
          CASE WHEN dr.from_document_id = COALESCE(%s, dr.from_document_id)
               THEN dr.to_document_id ELSE dr.from_document_id END AS related_document_id,
          CASE WHEN dr.from_document_id = COALESCE(%s, dr.from_document_id)
               THEN to_doc.title ELSE from_doc.title END AS related_title,
          dr.relationship_type::text AS relationship_type,
          dr.status,
          CASE WHEN dr.from_document_id = COALESCE(%s, dr.from_document_id)
               THEN 'from' ELSE 'to' END AS direction,
          dr.confidence,
          dr.source_engine::text AS source_engine,
          dr.evidence_json,
          dr.comment,
          dr.review_task_id,
          dr.created_at
        FROM document_relationships dr
        JOIN documents from_doc ON from_doc.id = dr.from_document_id
        JOIN documents to_doc ON to_doc.id = dr.to_document_id
        WHERE from_doc.household_id = %s
          AND to_doc.household_id = %s
          AND (%s::uuid IS NULL OR %s IN (dr.from_document_id, dr.to_document_id))
          AND (%s::text IS NULL OR dr.status = %s)
          AND document_is_readable(from_doc.id, %s, %s, %s)
          AND document_is_readable(to_doc.id, %s, %s, %s)
        ORDER BY
          CASE dr.status WHEN 'suggested' THEN 0 WHEN 'confirmed' THEN 1 ELSE 2 END,
          dr.created_at DESC,
          dr.id
        LIMIT %s
        """,
        (
            document_id,
            document_id,
            document_id,
            document_id,
            access.household_id,
            access.household_id,
            document_id,
            document_id,
            status,
            status,
            *document_read_access_params(access),
            *document_read_access_params(access),
            limit,
        ),
    )
    return cast(list[Row], cur.fetchall())


def get_relationship_row(
    cur: Any,
    *,
    relationship_id: UUID,
    access: DocumentAccessContext,
) -> Row | None:
    cur.execute(
        """
        SELECT dr.*
        FROM document_relationships dr
        JOIN documents from_doc ON from_doc.id = dr.from_document_id
        JOIN documents to_doc ON to_doc.id = dr.to_document_id
        WHERE dr.id = %s
          AND from_doc.household_id = %s
          AND to_doc.household_id = %s
          AND document_is_readable(from_doc.id, %s, %s, %s)
          AND document_is_readable(to_doc.id, %s, %s, %s)
        """,
        (
            relationship_id,
            access.household_id,
            access.household_id,
            *document_read_access_params(access),
            *document_read_access_params(access),
        ),
    )
    return cast(Row | None, cur.fetchone())


def document_is_writable(cur: Any, *, document_id: UUID, access: DocumentAccessContext) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM documents d
        WHERE d.id = %s
          AND d.deleted_at IS NULL
          AND d.household_id = %s
          AND document_is_readable(d.id, %s, %s, %s)
          AND (d.owner_user_id = %s OR %s IN ('owner', 'admin'))
        """,
        (
            document_id,
            access.household_id,
            *document_read_access_params(access),
            access.user_id,
            access.household_role,
        ),
    )
    return cur.fetchone() is not None


def upsert_relationship(
    cur: Any,
    *,
    from_document_id: UUID,
    to_document_id: UUID,
    relationship_type: str,
    status: str,
    source_engine: str,
    confidence: float | None,
    evidence: Sequence[Mapping[str, Any]],
    comment: str | None,
    actor_user_id: UUID | None,
    review_task_id: UUID | None = None,
) -> Row:
    existing = _active_relationship_row(
        cur,
        from_document_id=from_document_id,
        to_document_id=to_document_id,
        relationship_type=relationship_type,
    )
    if existing:
        if existing["status"] == "confirmed" and status == "suggested":
            return existing
        cur.execute(
            """
            UPDATE document_relationships
            SET status = %s,
                confidence = COALESCE(%s, confidence),
                evidence_json = CASE
                  WHEN %s::jsonb = '[]'::jsonb THEN evidence_json ELSE %s::jsonb
                END,
                comment = COALESCE(%s, comment),
                review_task_id = COALESCE(%s, review_task_id),
                decided_by_user_id = CASE WHEN %s = 'confirmed' THEN %s ELSE decided_by_user_id END,
                decided_at = CASE WHEN %s = 'confirmed' THEN now() ELSE decided_at END,
                updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (
                status,
                confidence,
                Jsonb(list(evidence)),
                Jsonb(list(evidence)),
                comment,
                review_task_id,
                status,
                actor_user_id,
                status,
                existing["id"],
            ),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Relationship update failed.")
        return cast(Row, row)

    cur.execute(
        """
        INSERT INTO document_relationships
          (
            from_document_id,
            to_document_id,
            relationship_type,
            source_engine,
            status,
            confidence,
            evidence_json,
            comment,
            review_task_id,
            created_by_user_id,
            decided_by_user_id,
            decided_at
          )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s,
          CASE WHEN %s = 'confirmed' THEN now() ELSE NULL END
        )
        RETURNING *
        """,
        (
            from_document_id,
            to_document_id,
            relationship_type,
            source_engine,
            status,
            confidence,
            Jsonb(list(evidence)),
            comment,
            review_task_id,
            actor_user_id,
            actor_user_id if status == "confirmed" else None,
            status,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Relationship insert failed.")
    return cast(Row, row)


def decide_relationship(
    cur: Any,
    *,
    relationship_id: UUID,
    status: str,
    actor_user_id: UUID,
    comment: str | None,
    access: DocumentAccessContext,
) -> Row | None:
    from lib.review.audit_repository import record_review_event, update_document_review_status

    row = get_relationship_row(cur, relationship_id=relationship_id, access=access)
    if not row:
        return None
    if not document_is_writable(cur, document_id=row["from_document_id"], access=access):
        return None
    if not document_is_writable(cur, document_id=row["to_document_id"], access=access):
        return None
    cur.execute(
        """
        UPDATE document_relationships
        SET status = %s,
            comment = COALESCE(%s, comment),
            decided_by_user_id = %s,
            decided_at = now(),
            updated_at = now()
        WHERE id = %s
        RETURNING *
        """,
        (status, comment, actor_user_id, relationship_id),
    )
    updated = cur.fetchone()
    if not updated:
        return None
    if row.get("review_task_id"):
        cur.execute(
            """
            UPDATE review_tasks
            SET status = 'resolved',
                updated_at = now()
            WHERE id = %s
            """,
            (row["review_task_id"],),
        )
    event_id = record_review_event(
        cur,
        document_id=cast(UUID, row["from_document_id"]),
        review_task_id=cast(UUID | None, row.get("review_task_id")),
        field_path=None,
        action="accept_relationship" if status == "confirmed" else "reject_relationship",
        old_value={"status": row["status"]},
        new_value={"status": status, "relationshipId": str(relationship_id)},
        actor_label=str(actor_user_id),
        reason=comment,
    )
    del event_id
    update_document_review_status(cur, cast(UUID, row["from_document_id"]))
    update_document_review_status(cur, cast(UUID, row["to_document_id"]))
    return cast(Row, updated)


def create_relationship_review_task(
    cur: Any,
    *,
    document_id: UUID,
    relationship_type: str,
    related_document_id: UUID,
    confidence: float | None,
    reason: str,
) -> UUID:
    cur.execute(
        """
        INSERT INTO review_tasks (document_id, task_type, status, priority, reason, metadata_json)
        SELECT %s, 'relationship_suggestion', 'open', %s, %s, %s::jsonb
        WHERE NOT EXISTS (
          SELECT 1
          FROM review_tasks
          WHERE document_id = %s
            AND task_type = 'relationship_suggestion'
            AND status IN ('open', 'in_progress')
            AND metadata_json->>'relatedDocumentId' = %s
            AND metadata_json->>'relationshipType' = %s
        )
        RETURNING id
        """,
        (
            document_id,
            75 if (confidence or 0) >= 0.85 else 60,
            reason,
            Jsonb(
                {
                    "relationshipType": relationship_type,
                    "relatedDocumentId": str(related_document_id),
                    "confidence": confidence,
                }
            ),
            document_id,
            str(related_document_id),
            relationship_type,
        ),
    )
    row = cur.fetchone()
    if row:
        return cast(UUID, row["id"])
    cur.execute(
        """
        SELECT id
        FROM review_tasks
        WHERE document_id = %s
          AND task_type = 'relationship_suggestion'
          AND status IN ('open', 'in_progress')
          AND metadata_json->>'relatedDocumentId' = %s
          AND metadata_json->>'relationshipType' = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (document_id, str(related_document_id), relationship_type),
    )
    existing = cur.fetchone()
    if not existing:
        raise RuntimeError("Relationship review task insert failed.")
    return cast(UUID, existing["id"])


def record_relationship_audit(
    cur: Any,
    *,
    event_name: str,
    relationship_id: UUID,
    document_id: UUID,
    actor_label: str,
    payload: Mapping[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO audit_events
          (entity_type, entity_id, document_id, event_name, actor_label, payload_json)
        VALUES ('document_relationship', %s, %s, %s, %s, %s::jsonb)
        """,
        (relationship_id, document_id, event_name, actor_label, Jsonb(dict(payload))),
    )


def relationship_context_rows(cur: Any, *, document_id: UUID, household_id: UUID) -> list[Row]:
    cur.execute(
        """
        SELECT
          d.id,
          d.household_id,
          d.title,
          d.document_family::text AS family,
          d.document_date,
          d.original_sha256,
          d.counterparty_display,
          COALESCE(
            array_agg(DISTINCT c.display_name) FILTER (WHERE c.id IS NOT NULL),
            ARRAY[]::text[]
          ) AS contacts
        FROM documents d
        LEFT JOIN document_contacts dc ON dc.document_id = d.id
        LEFT JOIN contacts c ON c.id = dc.contact_id
        WHERE d.household_id = %s
          AND d.deleted_at IS NULL
          AND (
            d.id = %s
            OR d.original_sha256 = (SELECT original_sha256 FROM documents WHERE id = %s)
            OR EXISTS (
              SELECT 1
              FROM document_contacts target_dc
              JOIN document_contacts other_dc ON other_dc.contact_id = target_dc.contact_id
              WHERE target_dc.document_id = %s
                AND other_dc.document_id = d.id
            )
          )
        GROUP BY d.id
        ORDER BY (d.id = %s) DESC, d.created_at DESC
        LIMIT 100
        """,
        (household_id, document_id, document_id, document_id, document_id),
    )
    return cast(list[Row], cur.fetchall())


def _active_relationship_row(
    cur: Any,
    *,
    from_document_id: UUID,
    to_document_id: UUID,
    relationship_type: str,
) -> Row | None:
    cur.execute(
        """
        SELECT *
        FROM document_relationships
        WHERE relationship_type = %s
          AND status IN ('suggested', 'confirmed')
          AND (
            (from_document_id = %s AND to_document_id = %s)
            OR (from_document_id = %s AND to_document_id = %s)
          )
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (relationship_type, from_document_id, to_document_id, to_document_id, from_document_id),
    )
    return cast(Row | None, cur.fetchone())
