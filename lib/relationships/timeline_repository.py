from __future__ import annotations

from typing import Any, TypeAlias, cast
from uuid import UUID

from lib.documents.access_policy import DocumentAccessContext, document_read_access_params
from lib.relationships.visibility_sql import readable_counterpart_params

Row: TypeAlias = dict[str, Any]


def timeline_rows(
    cur: Any,
    *,
    access: DocumentAccessContext,
    document_id: UUID | None = None,
    contact_id: UUID | None = None,
    limit: int = 200,
) -> list[Row]:
    cur.execute(
        """
        WITH visible_docs AS (
          SELECT DISTINCT d.id, d.title, d.document_date, d.created_at, d.metadata_json
          FROM documents d
          LEFT JOIN document_contacts dc ON dc.document_id = d.id
          WHERE d.household_id = %s
            AND d.deleted_at IS NULL
            AND (%s::uuid IS NULL OR d.id = %s)
            AND (%s::uuid IS NULL OR dc.contact_id = %s)
            AND document_is_readable(d.id, %s, %s, %s)
        ),
        relationship_events AS (
          SELECT
            'relationship-' || dr.id::text AS id,
            'relationship'::text AS event_type,
            dr.created_at::date AS occurred_on,
            (
              dr.relationship_type::text || ' · ' || from_doc.title || ' ↔ ' || to_doc.title
            ) AS title,
            dr.from_document_id AS document_id,
            from_doc.title AS document_title,
            dr.id AS relationship_id,
            NULL::uuid AS contact_id,
            NULL::text AS contact_name,
            NULL::uuid AS deadline_id,
            dr.status,
            jsonb_build_object(
              'relatedDocumentId',
              dr.to_document_id,
              'relationshipType',
              dr.relationship_type::text
            ) AS metadata_json
          FROM document_relationships dr
          JOIN documents from_doc ON from_doc.id = dr.from_document_id
          JOIN documents to_doc ON to_doc.id = dr.to_document_id
          WHERE dr.status <> 'rejected'
            AND (%s::uuid IS NULL OR %s IN (dr.from_document_id, dr.to_document_id))
            AND (
              %s::uuid IS NULL
              OR EXISTS (
                SELECT 1
                FROM visible_docs vd
                WHERE vd.id IN (dr.from_document_id, dr.to_document_id)
              )
            )
            AND from_doc.household_id = %s
            AND to_doc.household_id = %s
            AND document_is_readable(from_doc.id, %s, %s, %s)
            AND document_is_readable(to_doc.id, %s, %s, %s)
        ),
        deadline_events AS (
          SELECT
            'deadline-' || dd.id::text AS id,
            'deadline'::text AS event_type,
            dd.due_on AS occurred_on,
            (dd.deadline_type::text || ' · ' || d.title) AS title,
            dd.document_id,
            d.title AS document_title,
            NULL::uuid AS relationship_id,
            NULL::uuid AS contact_id,
            NULL::text AS contact_name,
            dd.id AS deadline_id,
            dd.status,
            dd.metadata_json
          FROM document_deadlines dd
          JOIN documents d ON d.id = dd.document_id
          WHERE d.household_id = %s
            AND d.deleted_at IS NULL
            AND dd.status IN ('open', 'due_soon', 'overdue', 'needs_review')
            AND (%s::uuid IS NULL OR dd.document_id = %s)
            AND (%s::uuid IS NULL OR EXISTS (
              SELECT 1
              FROM visible_docs vd
              WHERE vd.id = dd.document_id
            ))
            AND document_is_readable(d.id, %s, %s, %s)
        ),
        document_events AS (
          SELECT
            'document-' || vd.id::text AS id,
            'document'::text AS event_type,
            COALESCE(vd.document_date, vd.created_at::date) AS occurred_on,
            vd.title,
            vd.id AS document_id,
            vd.title AS document_title,
            NULL::uuid AS relationship_id,
            NULL::uuid AS contact_id,
            NULL::text AS contact_name,
            NULL::uuid AS deadline_id,
            'active'::text AS status,
            vd.metadata_json
          FROM visible_docs vd
        )
        SELECT *
        FROM (
          SELECT * FROM document_events
          UNION ALL
          SELECT * FROM relationship_events
          UNION ALL
          SELECT * FROM deadline_events
        ) timeline
        ORDER BY occurred_on DESC, title
        LIMIT %s
        """,
        (
            access.household_id,
            document_id,
            document_id,
            contact_id,
            contact_id,
            *document_read_access_params(access),
            document_id,
            document_id,
            contact_id,
            access.household_id,
            access.household_id,
            *document_read_access_params(access),
            *document_read_access_params(access),
            access.household_id,
            document_id,
            document_id,
            contact_id,
            *document_read_access_params(access),
            limit,
        ),
    )
    return cast(list[Row], cur.fetchall())


def smart_view_counts(cur: Any, *, access: DocumentAccessContext) -> dict[str, int]:
    params = document_read_access_params(access)
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM document_deadlines dd
              WHERE dd.document_id = d.id
                AND dd.status IN ('open', 'due_soon', 'overdue', 'needs_review')
            )
          )::int AS open_deadlines,
          COUNT(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM document_deadlines dd
              WHERE dd.document_id = d.id
                AND dd.deadline_type = 'warranty_expiration'
                AND dd.status IN ('open', 'due_soon', 'overdue', 'needs_review')
                AND dd.due_on <= current_date + interval '90 days'
            )
          )::int AS warranties_expiring_soon,
          COUNT(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM document_deadlines dd
              WHERE dd.document_id = d.id
                AND dd.deadline_type = 'renewal_date'
                AND dd.status IN ('open', 'due_soon', 'overdue', 'needs_review')
            )
          )::int AS renewals,
          COUNT(*) FILTER (
            WHERE EXISTS (
              SELECT 1 FROM document_relationships dr
              WHERE d.id IN (dr.from_document_id, dr.to_document_id)
                AND dr.status = 'suggested'
                AND document_is_readable(
                  CASE
                    WHEN dr.from_document_id = d.id THEN dr.to_document_id
                    ELSE dr.from_document_id
                  END,
                  %s,
                  %s,
                  %s
                )
            )
          )::int AS relationship_suggestions,
          COUNT(*) FILTER (WHERE d.review_status = 'needs_review')::int AS needs_review,
          COUNT(*) FILTER (WHERE d.document_family::text = 'tax_document')::int AS tax_relevant,
          COUNT(*) FILTER (
            WHERE d.document_family::text IN ('medical_eob', 'medical_bill')
              AND NOT EXISTS (
                SELECT 1 FROM document_relationships dr
                WHERE d.id IN (dr.from_document_id, dr.to_document_id)
                  AND dr.status IN ('suggested', 'confirmed')
                  AND document_is_readable(
                    CASE
                      WHEN dr.from_document_id = d.id THEN dr.to_document_id
                      ELSE dr.from_document_id
                    END,
                    %s,
                    %s,
                    %s
                  )
              )
          )::int AS unmatched_medical_docs
        FROM documents d
        WHERE d.household_id = %s
          AND d.deleted_at IS NULL
          AND document_is_readable(d.id, %s, %s, %s)
        """,
        (
            *readable_counterpart_params(access),
            *readable_counterpart_params(access),
            access.household_id,
            *params,
        ),
    )
    row = cur.fetchone() or {}
    return {key: int(row.get(key) or 0) for key in _SMART_VIEW_KEYS}


_SMART_VIEW_KEYS = (
    "open_deadlines",
    "warranties_expiring_soon",
    "renewals",
    "relationship_suggestions",
    "needs_review",
    "tax_relevant",
    "unmatched_medical_docs",
)
