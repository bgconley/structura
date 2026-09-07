from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.review.errors import ReviewRepositoryError


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
          updated_at = GREATEST(
            clock_timestamp(), canonical_fields.updated_at + interval '1 microsecond'
          )
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
