from __future__ import annotations

from typing import Any, TypeAlias, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.documents.access_policy import DocumentAccessContext, document_read_access_params

Row: TypeAlias = dict[str, Any]


def list_contacts(
    cur: Any,
    *,
    household_id: UUID,
    query: str | None = None,
    contact_type: str | None = None,
) -> list[Row]:
    like_query = f"%{query.casefold()}%" if query else None
    cur.execute(
        """
        SELECT
          c.id,
          c.contact_type,
          c.display_name,
          c.normalized_name::text AS normalized_name,
          c.identifiers_json,
          COALESCE(
            array_agg(ca.alias::text ORDER BY ca.alias) FILTER (WHERE ca.id IS NOT NULL),
            ARRAY[]::text[]
          ) AS aliases,
          COALESCE(COUNT(DISTINCT dc.document_id), 0)::int AS linked_document_count
        FROM contacts c
        LEFT JOIN contact_aliases ca ON ca.contact_id = c.id
        LEFT JOIN document_contacts dc ON dc.contact_id = c.id
        WHERE c.household_id = %s
          AND (%s::text IS NULL OR c.contact_type = %s)
          AND (
            %s::text IS NULL
            OR lower(c.display_name) LIKE %s
            OR lower(c.normalized_name::text) LIKE %s
            OR EXISTS (
              SELECT 1
              FROM contact_aliases query_alias
              WHERE query_alias.contact_id = c.id
                AND lower(query_alias.alias::text) LIKE %s
            )
            OR lower(c.identifiers_json::text) LIKE %s
          )
        GROUP BY c.id
        ORDER BY lower(c.display_name), c.id
        LIMIT 200
        """,
        (
            household_id,
            contact_type,
            contact_type,
            like_query,
            like_query,
            like_query,
            like_query,
            like_query,
        ),
    )
    return cast(list[Row], cur.fetchall())


def get_contact(cur: Any, *, contact_id: UUID, household_id: UUID) -> Row | None:
    cur.execute(
        """
        SELECT
          id,
          contact_type,
          display_name,
          normalized_name::text AS normalized_name,
          identifiers_json
        FROM contacts
        WHERE id = %s
          AND household_id = %s
        """,
        (contact_id, household_id),
    )
    return cast(Row | None, cur.fetchone())


def insert_contact(
    cur: Any,
    *,
    household_id: UUID,
    contact_type: str,
    display_name: str,
    normalized_name: str,
    identifiers: dict[str, Any],
) -> Row | None:
    cur.execute(
        """
        INSERT INTO contacts
          (household_id, contact_type, display_name, normalized_name, identifiers_json)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        RETURNING
          id,
          contact_type,
          display_name,
          normalized_name::text AS normalized_name,
          identifiers_json
        """,
        (household_id, contact_type, display_name, normalized_name, Jsonb(identifiers)),
    )
    return cast(Row | None, cur.fetchone())


def update_contact(
    cur: Any,
    *,
    contact_id: UUID,
    household_id: UUID,
    contact_type: str,
    display_name: str,
    normalized_name: str,
    identifiers: dict[str, Any],
) -> Row | None:
    cur.execute(
        """
        UPDATE contacts
        SET contact_type = %s,
            display_name = %s,
            normalized_name = %s,
            identifiers_json = %s::jsonb,
            updated_at = now()
        WHERE id = %s
          AND household_id = %s
        RETURNING
          id,
          contact_type,
          display_name,
          normalized_name::text AS normalized_name,
          identifiers_json
        """,
        (contact_type, display_name, normalized_name, Jsonb(identifiers), contact_id, household_id),
    )
    return cast(Row | None, cur.fetchone())


def replace_aliases(cur: Any, *, contact_id: UUID, aliases: list[str]) -> None:
    cur.execute("DELETE FROM contact_aliases WHERE contact_id = %s", (contact_id,))
    for alias in aliases:
        cur.execute(
            """
            INSERT INTO contact_aliases (contact_id, alias, source)
            VALUES (%s, %s, 'user')
            ON CONFLICT (contact_id, alias) DO NOTHING
            """,
            (contact_id, alias),
        )


def aliases_for_contact(cur: Any, contact_id: UUID) -> list[str]:
    cur.execute(
        "SELECT alias::text AS alias FROM contact_aliases WHERE contact_id = %s ORDER BY alias",
        (contact_id,),
    )
    return [str(row["alias"]) for row in cur.fetchall()]


def lock_writable_document(
    cur: Any,
    *,
    document_id: UUID,
    access: DocumentAccessContext,
) -> Row | None:
    cur.execute(
        """
        SELECT id, title, household_id
        FROM documents d
        WHERE d.id = %s
          AND d.deleted_at IS NULL
          AND document_is_readable(d.id, %s, %s, %s)
          AND (d.owner_user_id = %s OR %s IN ('owner', 'admin'))
        FOR UPDATE
        """,
        (
            document_id,
            *document_read_access_params(access),
            access.user_id,
            access.household_role,
        ),
    )
    return cast(Row | None, cur.fetchone())


def upsert_document_contact(
    cur: Any,
    *,
    document_id: UUID,
    contact_id: UUID,
    role_name: str,
    evidence: dict[str, Any],
    confidence: float | None,
) -> Row | None:
    cur.execute(
        """
        INSERT INTO document_contacts
          (document_id, contact_id, role_name, evidence_json, confidence)
        VALUES (%s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (document_id, contact_id, role_name)
        DO UPDATE SET evidence_json = EXCLUDED.evidence_json,
                      confidence = EXCLUDED.confidence
        RETURNING id, document_id, contact_id, role_name, evidence_json, confidence
        """,
        (document_id, contact_id, role_name, Jsonb(evidence), confidence),
    )
    return cast(Row | None, cur.fetchone())


def list_document_contacts(
    cur: Any,
    *,
    document_id: UUID,
    access: DocumentAccessContext,
) -> list[Row]:
    cur.execute(
        """
        SELECT
          dc.id,
          dc.document_id,
          dc.contact_id,
          c.display_name,
          dc.role_name,
          dc.evidence_json,
          dc.confidence
        FROM document_contacts dc
        JOIN contacts c ON c.id = dc.contact_id
        JOIN documents d ON d.id = dc.document_id
        WHERE dc.document_id = %s
          AND c.household_id = %s
          AND document_is_readable(d.id, %s, %s, %s)
        ORDER BY dc.role_name, lower(c.display_name)
        """,
        (document_id, access.household_id, *document_read_access_params(access)),
    )
    return cast(list[Row], cur.fetchall())


def merge_suggestions(cur: Any, *, household_id: UUID) -> list[Row]:
    cur.execute(
        """
        SELECT left_contact.id AS source_contact_id,
               right_contact.id AS target_contact_id,
               'normalized_name_match' AS reason,
               0.92::float AS confidence
        FROM contacts left_contact
        JOIN contacts right_contact
          ON right_contact.household_id = left_contact.household_id
         AND right_contact.normalized_name = left_contact.normalized_name
         AND right_contact.id < left_contact.id
        WHERE left_contact.household_id = %s
          AND left_contact.normalized_name IS NOT NULL
        ORDER BY left_contact.created_at DESC
        LIMIT 100
        """,
        (household_id,),
    )
    return cast(list[Row], cur.fetchall())


def merge_contacts(
    cur: Any,
    *,
    source_contact_id: UUID,
    target_contact_id: UUID,
    household_id: UUID,
) -> Row | None:
    source = get_contact(cur, contact_id=source_contact_id, household_id=household_id)
    target = get_contact(cur, contact_id=target_contact_id, household_id=household_id)
    if not source or not target:
        return None
    source_aliases = aliases_for_contact(cur, source_contact_id)
    target_aliases = set(alias.casefold() for alias in aliases_for_contact(cur, target_contact_id))
    for alias in [str(source["display_name"]), *source_aliases]:
        if alias.casefold() not in target_aliases:
            cur.execute(
                """
                INSERT INTO contact_aliases (contact_id, alias, source)
                VALUES (%s, %s, 'merge')
                ON CONFLICT (contact_id, alias) DO NOTHING
                """,
                (target_contact_id, alias),
            )
    cur.execute(
        """
        UPDATE document_contacts dc
        SET contact_id = %s
        WHERE contact_id = %s
          AND NOT EXISTS (
            SELECT 1
            FROM document_contacts existing
            WHERE existing.document_id = dc.document_id
              AND existing.contact_id = %s
              AND existing.role_name = dc.role_name
          )
        """,
        (target_contact_id, source_contact_id, target_contact_id),
    )
    cur.execute("DELETE FROM document_contacts WHERE contact_id = %s", (source_contact_id,))
    cur.execute(
        """
        UPDATE contacts target
        SET identifiers_json = target.identifiers_json || source.identifiers_json,
            updated_at = now()
        FROM contacts source
        WHERE target.id = %s
          AND source.id = %s
        """,
        (target_contact_id, source_contact_id),
    )
    cur.execute(
        "DELETE FROM contacts WHERE id = %s AND household_id = %s",
        (source_contact_id, household_id),
    )
    return get_contact(cur, contact_id=target_contact_id, household_id=household_id)


def record_contact_audit(
    cur: Any,
    *,
    event_name: str,
    contact_id: UUID,
    actor_label: str,
    payload: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO audit_events (entity_type, entity_id, event_name, actor_label, payload_json)
        VALUES ('contact', %s, %s, %s, %s::jsonb)
        """,
        (contact_id, event_name, actor_label, Jsonb(payload)),
    )
