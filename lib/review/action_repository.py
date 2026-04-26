from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.contracts import CanonicalField
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.extraction.candidate_repository import (
    candidate_value_json,
    typed_value_columns,
)
from lib.review.access import assert_readable
from lib.review.audit_repository import (
    close_field_review_tasks,
    record_history,
    record_review_event,
    update_document_review_status,
)
from lib.review.errors import ReviewRepositoryError
from lib.review.mappers import canonical_field_from_row, canonical_value


def get_field_candidate(
    cur: Any,
    *,
    document_id: UUID,
    candidate_id: UUID,
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT *
        FROM field_candidates
        WHERE id = %s
          AND document_id = %s
        """,
        (candidate_id, document_id),
    )
    return cast(dict[str, Any] | None, cur.fetchone())


def upsert_human_canonical_field(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    field_path: str,
    value_type: str,
    value: object,
    evidence: list[dict[str, Any]],
    ordinal: int = 1,
    currency: str | None = None,
    selected_candidate_id: UUID | None = None,
    source_kind: str = "human",
    reason: str | None = None,
) -> tuple[CanonicalField, UUID]:
    typed = typed_value_columns(value_type, _typed_value_input(value_type, value, currency))
    if currency:
        typed["currency_code"] = currency
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_readable(cur, document_id, access)
            previous = _canonical_row(cur, document_id, field_path, ordinal)
            canonical_id = _upsert_canonical_row(
                cur,
                document_id=document_id,
                selected_candidate_id=selected_candidate_id,
                field_path=field_path,
                ordinal=ordinal,
                value_type=value_type,
                typed=typed,
                source_kind=source_kind,
                review_status="user_corrected" if source_kind == "human" else "user_confirmed",
                evidence=evidence,
                validation={"reviewed": True},
                actor_user_id=actor_user_id,
            )
            event_id = record_review_event(
                cur,
                document_id=document_id,
                review_task_id=None,
                field_path=field_path,
                action="correct_field" if source_kind == "human" else "confirm_field",
                old_value=canonical_value(previous) if previous else None,
                new_value={"valueType": value_type, "value": value, "currency": currency},
                actor_label=str(actor_user_id),
                reason=reason,
            )
            record_history(
                cur,
                document_id=document_id,
                canonical_field_id=canonical_id,
                field_path=field_path,
                action="human_corrected" if source_kind == "human" else "human_confirmed",
                old_value=canonical_value(previous) if previous else None,
                new_value={"valueType": value_type, "value": value, "currency": currency},
                actor_user_id=actor_user_id,
                reason=reason,
            )
            close_field_review_tasks(cur, document_id, field_path)
            update_document_review_status(cur, document_id)
            cur.execute("SELECT * FROM canonical_fields WHERE id = %s", (canonical_id,))
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ReviewRepositoryError("Canonical field write failed.")
    return canonical_field_from_row(row), event_id


def confirm_candidate(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    candidate_id: UUID,
    reason: str | None,
) -> UUID:
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_readable(cur, document_id, access)
            candidate = get_field_candidate(cur, document_id=document_id, candidate_id=candidate_id)
            if not candidate:
                raise ReviewRepositoryError("Candidate not found.")
            previous = _canonical_row(
                cur, document_id, candidate["field_path"], candidate["ordinal"]
            )
            canonical_id = _upsert_canonical_row(
                cur,
                document_id=document_id,
                selected_candidate_id=candidate_id,
                field_path=candidate["field_path"],
                ordinal=candidate["ordinal"],
                value_type=candidate["value_type"],
                typed=candidate,
                source_kind="candidate",
                review_status="user_confirmed",
                evidence=candidate["evidence_json"],
                validation=candidate["validation_json"],
                actor_user_id=actor_user_id,
            )
            cur.execute(
                "UPDATE field_candidates SET status = 'promoted', updated_at = now() WHERE id = %s",
                (candidate_id,),
            )
            event_id = record_review_event(
                cur,
                document_id=document_id,
                review_task_id=None,
                field_path=candidate["field_path"],
                action="confirm_field",
                old_value=canonical_value(previous) if previous else None,
                new_value=candidate_value_json(candidate),
                actor_label=str(actor_user_id),
                reason=reason,
            )
            record_history(
                cur,
                document_id=document_id,
                canonical_field_id=canonical_id,
                field_path=candidate["field_path"],
                action="human_confirmed",
                old_value=canonical_value(previous) if previous else None,
                new_value=candidate_value_json(candidate),
                actor_user_id=actor_user_id,
                reason=reason,
            )
            close_field_review_tasks(cur, document_id, candidate["field_path"])
            update_document_review_status(cur, document_id)
        conn.commit()
    return event_id


def reject_field(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    field_path: str,
    reason: str | None,
) -> UUID:
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_readable(cur, document_id, access)
            cur.execute(
                """
                UPDATE field_candidates
                SET status = 'rejected',
                    updated_at = now()
                WHERE document_id = %s
                  AND field_path = %s
                  AND status <> 'rejected'
                """,
                (document_id, field_path),
            )
            previous = _canonical_row(cur, document_id, field_path, 1)
            cur.execute(
                """
                UPDATE canonical_fields
                SET review_status = 'rejected',
                    updated_at = now()
                WHERE document_id = %s
                  AND field_path = %s
                """,
                (document_id, field_path),
            )
            event_id = record_review_event(
                cur,
                document_id=document_id,
                review_task_id=None,
                field_path=field_path,
                action="reject_field",
                old_value=canonical_value(previous) if previous else None,
                new_value={"status": "rejected"},
                actor_label=str(actor_user_id),
                reason=reason,
            )
            if previous:
                record_history(
                    cur,
                    document_id=document_id,
                    canonical_field_id=previous["id"],
                    field_path=field_path,
                    action="human_rejected",
                    old_value=canonical_value(previous),
                    new_value={"status": "rejected"},
                    actor_user_id=actor_user_id,
                    reason=reason,
                )
            close_field_review_tasks(cur, document_id, field_path)
            update_document_review_status(cur, document_id)
        conn.commit()
    return event_id


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
            assert_readable(cur, document_id, access)
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
            assert_readable(cur, document_id, access)
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
    target_schema_name: str,
    reason: str | None,
) -> UUID:
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_readable(cur, document_id, access)
            event_id = record_review_event(
                cur,
                document_id=document_id,
                review_task_id=None,
                field_path=None,
                action="rerun_extraction",
                old_value=None,
                new_value={"target_schema_name": target_schema_name},
                actor_label=str(actor_user_id),
                reason=reason,
            )
        conn.commit()
    return event_id


def _canonical_row(
    cur: Any, document_id: UUID, field_path: str, ordinal: int
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT *
        FROM canonical_fields
        WHERE document_id = %s
          AND field_path = %s
          AND ordinal = %s
        """,
        (document_id, field_path, ordinal),
    )
    return cast(dict[str, Any] | None, cur.fetchone())


def _typed_value_input(value_type: str, value: object, currency: str | None) -> object:
    if value_type != "money":
        return value
    if isinstance(value, Mapping):
        money_value = dict(value)
        if currency and not money_value.get("currency"):
            money_value["currency"] = currency
        return money_value
    return {"amount": value, "currency": currency}


def _upsert_canonical_row(
    cur: Any,
    *,
    document_id: UUID,
    selected_candidate_id: UUID | None,
    field_path: str,
    ordinal: int,
    value_type: str,
    typed: Mapping[str, Any],
    source_kind: str,
    review_status: str,
    evidence: object,
    validation: object,
    actor_user_id: UUID,
) -> UUID:
    cur.execute(
        """
        INSERT INTO canonical_fields
          (
            document_id, selected_candidate_id, field_path, ordinal, value_type,
            text_value, integer_value, numeric_value, boolean_value, date_value,
            timestamp_value, json_value, currency_code, source_kind, review_status,
            evidence_json, validation_json, accepted_by_user_id, accepted_at
          )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
          %s, %s, %s, %s::jsonb, %s::jsonb, %s, now()
        )
        ON CONFLICT (document_id, field_path, ordinal)
        DO UPDATE SET
          selected_candidate_id = EXCLUDED.selected_candidate_id,
          value_type = EXCLUDED.value_type,
          text_value = EXCLUDED.text_value,
          integer_value = EXCLUDED.integer_value,
          numeric_value = EXCLUDED.numeric_value,
          boolean_value = EXCLUDED.boolean_value,
          date_value = EXCLUDED.date_value,
          timestamp_value = EXCLUDED.timestamp_value,
          json_value = EXCLUDED.json_value,
          currency_code = EXCLUDED.currency_code,
          source_kind = EXCLUDED.source_kind,
          review_status = EXCLUDED.review_status,
          evidence_json = EXCLUDED.evidence_json,
          validation_json = EXCLUDED.validation_json,
          accepted_by_user_id = EXCLUDED.accepted_by_user_id,
          accepted_at = EXCLUDED.accepted_at,
          updated_at = now()
        RETURNING id
        """,
        (
            document_id,
            selected_candidate_id,
            field_path,
            ordinal,
            value_type,
            typed.get("text_value"),
            typed.get("integer_value"),
            typed.get("numeric_value"),
            typed.get("boolean_value"),
            typed.get("date_value"),
            typed.get("timestamp_value"),
            Jsonb(typed.get("json_value")),
            typed.get("currency_code"),
            source_kind,
            review_status,
            Jsonb(evidence),
            Jsonb(validation),
            actor_user_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ReviewRepositoryError("Canonical field upsert failed.")
    return cast(UUID, row["id"])
