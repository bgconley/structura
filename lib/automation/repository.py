from __future__ import annotations

from typing import Any, TypeAlias, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.documents.access_policy import DocumentAccessContext, document_read_access_params

Row: TypeAlias = dict[str, Any]


def list_filing_rules(cur: Any, *, household_id: UUID) -> list[Row]:
    cur.execute(
        """
        SELECT id, name, description, enabled, priority, review_required,
               conditions_json, actions_json, last_run_at
        FROM filing_rules
        WHERE household_id = %s
        ORDER BY enabled DESC, priority DESC, lower(name), id
        """,
        (household_id,),
    )
    return cast(list[Row], cur.fetchall())


def get_filing_rule(cur: Any, *, rule_id: UUID, household_id: UUID) -> Row | None:
    cur.execute(
        """
        SELECT id, name, description, enabled, priority, review_required,
               conditions_json, actions_json, last_run_at
        FROM filing_rules
        WHERE id = %s
          AND household_id = %s
        """,
        (rule_id, household_id),
    )
    return cast(Row | None, cur.fetchone())


def upsert_filing_rule(
    cur: Any,
    *,
    rule_id: UUID | None,
    household_id: UUID,
    name: str,
    description: str | None,
    enabled: bool,
    priority: int,
    review_required: bool,
    conditions: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    created_by_user_id: UUID,
) -> Row | None:
    if rule_id:
        cur.execute(
            """
            UPDATE filing_rules
            SET name = %s,
                description = %s,
                enabled = %s,
                priority = %s,
                review_required = %s,
                conditions_json = %s::jsonb,
                actions_json = %s::jsonb,
                updated_at = now()
            WHERE id = %s
              AND household_id = %s
            RETURNING id, name, description, enabled, priority, review_required,
                      conditions_json, actions_json, last_run_at
            """,
            (
                name,
                description,
                enabled,
                priority,
                review_required,
                Jsonb(conditions),
                Jsonb(actions),
                rule_id,
                household_id,
            ),
        )
        return cast(Row | None, cur.fetchone())
    cur.execute(
        """
        INSERT INTO filing_rules
          (
            household_id,
            name,
            description,
            enabled,
            priority,
            review_required,
            conditions_json,
            actions_json,
            created_by_user_id
          )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        RETURNING id, name, description, enabled, priority, review_required,
                  conditions_json, actions_json, last_run_at
        """,
        (
            household_id,
            name,
            description,
            enabled,
            priority,
            review_required,
            Jsonb(conditions),
            Jsonb(actions),
            created_by_user_id,
        ),
    )
    return cast(Row | None, cur.fetchone())


def document_context_rows(
    cur: Any,
    *,
    access: DocumentAccessContext,
    document_ids: list[UUID] | None = None,
    limit: int = 100,
) -> list[Row]:
    cur.execute(
        """
        SELECT
          d.id,
          d.title,
          d.document_family::text AS document_family,
          d.document_subtype,
          d.counterparty_display,
          d.review_status::text AS review_status,
          d.sensitivity::text AS sensitivity,
          d.document_date,
          COALESCE((
            SELECT SUM(da.amount)::float
            FROM document_amounts da
            WHERE da.document_id = d.id
          ), NULL) AS amount_total,
          COALESCE((
            SELECT array_agg(t.name::text ORDER BY lower(t.name::text))
            FROM document_tags dt
            JOIN tags t ON t.id = dt.tag_id
            WHERE dt.document_id = d.id
          ), ARRAY[]::text[]) AS tags,
          COALESCE((
            SELECT array_agg(dfm.folder_id ORDER BY dfm.created_at)
            FROM document_folder_memberships dfm
            WHERE dfm.document_id = d.id
          ), ARRAY[]::uuid[]) AS folder_ids,
          COALESCE((
            SELECT array_agg(
              COALESCE(f.path_cache, '/' || f.name)
              ORDER BY COALESCE(f.path_cache, '/' || f.name)
            )
            FROM document_folder_memberships dfm
            JOIN folders f ON f.id = dfm.folder_id
            WHERE dfm.document_id = d.id
          ), ARRAY[]::text[]) AS folder_paths,
          COALESCE((
            SELECT array_agg(c.display_name ORDER BY lower(c.display_name))
            FROM document_contacts dc
            JOIN contacts c ON c.id = dc.contact_id
            WHERE dc.document_id = d.id
          ), ARRAY[]::text[]) AS contacts,
          COALESCE((
            SELECT jsonb_object_agg(
              cf.field_path,
              COALESCE(
                to_jsonb(cf.text_value),
                to_jsonb(cf.numeric_value),
                to_jsonb(cf.date_value),
                cf.json_value,
                to_jsonb(cf.boolean_value)
              )
            )
            FROM canonical_fields cf
            WHERE cf.document_id = d.id
              AND cf.review_status IN ('auto_accepted', 'user_confirmed', 'user_corrected')
          ), '{}'::jsonb) AS canonical_facts,
          COALESCE((
            SELECT string_agg(dc.text_content, E'\n' ORDER BY dc.chunk_index)
            FROM document_chunks dc
            WHERE dc.document_id = d.id
          ), '') AS search_text
        FROM documents d
        WHERE d.household_id = %s
          AND d.deleted_at IS NULL
          AND document_is_readable(d.id, %s, %s, %s)
          AND (%s::uuid[] IS NULL OR d.id = ANY(%s))
        ORDER BY d.updated_at DESC
        LIMIT %s
        """,
        (
            access.household_id,
            *document_read_access_params(access),
            document_ids,
            document_ids,
            limit,
        ),
    )
    return cast(list[Row], cur.fetchall())


def writable_folders(cur: Any, *, household_id: UUID, user_id: UUID) -> list[Row]:
    cur.execute(
        """
        SELECT f.id, COALESCE(f.path_cache, '/' || f.name) AS path
        FROM folders f
        WHERE (f.household_id = %s OR (f.household_id IS NULL AND f.is_system))
          AND f.folder_kind = 'manual'
          AND (
            f.acl_mode = 'household'
            OR f.owner_user_id = %s
            OR EXISTS (
              SELECT 1
              FROM folder_acl fa
              WHERE fa.folder_id = f.id
                AND fa.permission IN ('write', 'admin')
                AND (
                  (fa.principal_type = 'user' AND fa.principal_id = %s)
                  OR (fa.principal_type = 'household' AND fa.principal_id = %s)
                )
            )
          )
        """,
        (household_id, user_id, user_id, household_id),
    )
    return cast(list[Row], cur.fetchall())


def insert_rule_run(
    cur: Any,
    *,
    rule_id: UUID,
    document_id: UUID | None,
    mode: str,
    matched: bool,
    proposed_actions: list[dict[str, Any]],
    blocked_actions: list[dict[str, Any]],
    applied_actions: list[dict[str, Any]],
    explanation: dict[str, Any],
    decision_status: str = "recorded",
    actor_user_id: UUID | None = None,
) -> Row | None:
    cur.execute(
        """
        INSERT INTO filing_rule_runs
          (
            rule_id,
            document_id,
            mode,
            matched,
            proposed_actions_json,
            blocked_actions_json,
            applied_actions_json,
            explanation_json,
            decision_status,
            actor_user_id
          )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
        RETURNING id, rule_id, document_id, mode, matched, proposed_actions_json,
                  blocked_actions_json, applied_actions_json, explanation_json,
                  decision_status, created_at
        """,
        (
            rule_id,
            document_id,
            mode,
            matched,
            Jsonb(proposed_actions),
            Jsonb(blocked_actions),
            Jsonb(applied_actions),
            Jsonb(explanation),
            decision_status,
            actor_user_id,
        ),
    )
    row = cast(Row | None, cur.fetchone())
    cur.execute("UPDATE filing_rules SET last_run_at = now() WHERE id = %s", (rule_id,))
    return row


def create_or_refresh_suggestion_task(
    cur: Any,
    *,
    document_id: UUID,
    run_id: UUID,
    rule_name: str,
    explanation: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO review_tasks (document_id, task_type, status, priority, reason, metadata_json)
        SELECT %s, 'filing_suggestion', 'open', 65, %s, %s::jsonb
        WHERE NOT EXISTS (
          SELECT 1
          FROM review_tasks
          WHERE document_id = %s
            AND task_type = 'filing_suggestion'
            AND status = 'open'
            AND metadata_json->>'runId' = %s
        )
        """,
        (
            document_id,
            f"Suggested filing from rule {rule_name}",
            Jsonb({"runId": str(run_id), "ruleName": rule_name, "explanation": explanation}),
            document_id,
            str(run_id),
        ),
    )


def list_pending_suggestions(
    cur: Any,
    *,
    access: DocumentAccessContext,
) -> list[Row]:
    cur.execute(
        """
        SELECT
          frr.id AS run_id,
          frr.rule_id,
          fr.name AS rule_name,
          frr.document_id,
          d.title AS document_title,
          frr.proposed_actions_json,
          frr.blocked_actions_json,
          frr.explanation_json,
          frr.created_at
        FROM filing_rule_runs frr
        JOIN filing_rules fr ON fr.id = frr.rule_id
        JOIN documents d ON d.id = frr.document_id
        WHERE fr.household_id = %s
          AND frr.mode = 'suggest'
          AND frr.decision_status = 'pending'
          AND document_is_readable(d.id, %s, %s, %s)
        ORDER BY frr.created_at DESC
        LIMIT 200
        """,
        (access.household_id, *document_read_access_params(access)),
    )
    return cast(list[Row], cur.fetchall())


def get_pending_suggestion(
    cur: Any,
    *,
    run_id: UUID,
    household_id: UUID,
) -> Row | None:
    cur.execute(
        """
        SELECT frr.*, fr.name AS rule_name, fr.household_id
        FROM filing_rule_runs frr
        JOIN filing_rules fr ON fr.id = frr.rule_id
        WHERE frr.id = %s
          AND fr.household_id = %s
          AND frr.mode = 'suggest'
          AND frr.decision_status = 'pending'
        FOR UPDATE
        """,
        (run_id, household_id),
    )
    return cast(Row | None, cur.fetchone())


def mark_suggestion(
    cur: Any,
    *,
    run_id: UUID,
    decision_status: str,
    applied_actions: list[dict[str, Any]] | None = None,
) -> None:
    cur.execute(
        """
        UPDATE filing_rule_runs
        SET decision_status = %s,
            applied_actions_json = COALESCE(%s::jsonb, applied_actions_json),
            updated_at = now()
        WHERE id = %s
        """,
        (
            decision_status,
            Jsonb(applied_actions) if applied_actions is not None else None,
            run_id,
        ),
    )
    cur.execute(
        """
        UPDATE review_tasks
        SET status = 'resolved',
            updated_at = now()
        WHERE task_type = 'filing_suggestion'
          AND metadata_json->>'runId' = %s
          AND status = 'open'
        """,
        (str(run_id),),
    )


def record_audit(
    cur: Any,
    *,
    entity_type: str,
    entity_id: UUID | None,
    document_id: UUID | None = None,
    event_name: str,
    actor_label: str,
    payload: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO audit_events
          (entity_type, entity_id, document_id, event_name, actor_label, payload_json)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (entity_type, entity_id, document_id, event_name, actor_label, Jsonb(payload)),
    )
