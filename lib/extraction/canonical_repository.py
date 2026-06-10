from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.extraction.candidate_repository import (
    candidate_value_json,
    canonical_column_values,
)
from lib.extraction.canonical_promotion_policy import candidate_auto_promotion_rejection_reason
from lib.extraction.errors import ExtractionRepositoryError
from lib.extraction.models import ExtractionSourceDocument, ValidationReport
from lib.review.task_repository import upsert_review_task


def promote_candidates(
    cur: Any,
    *,
    source: ExtractionSourceDocument,
    extraction_id: UUID,
    candidates: list[dict[str, Any]],
    validation: ValidationReport,
    schema_name: str,
) -> int:
    if validation.needs_review or schema_name == "medical_eob":
        return 0
    promoted = 0
    for candidate in candidates:
        if candidate_auto_promotion_rejection_reason(candidate):
            continue
        if canonical_is_human_controlled(
            cur,
            source.document_id,
            candidate["field_path"],
            candidate["ordinal"],
        ):
            continue
        canonical_id = upsert_canonical_field(
            cur,
            document_id=source.document_id,
            selected_candidate_id=candidate["id"],
            field_path=candidate["field_path"],
            ordinal=candidate["ordinal"],
            value_type=candidate["value_type"],
            typed_values=candidate,
            source_kind="candidate",
            review_status="auto_accepted",
            evidence=candidate["evidence_json"],
            validation=candidate["validation_json"],
            accepted_by_user_id=None,
        )
        cur.execute(
            "UPDATE field_candidates SET status = 'promoted', updated_at = now() WHERE id = %s",
            (candidate["id"],),
        )
        record_canonical_history(
            cur,
            document_id=source.document_id,
            canonical_field_id=canonical_id,
            field_path=candidate["field_path"],
            action="auto_promoted",
            old_value=None,
            new_value=candidate_value_json(candidate),
            actor_user_id=None,
            reason="Phase 4 automatic promotion policy passed.",
        )
        promoted += 1
    return promoted


def create_review_tasks(
    cur: Any,
    *,
    source: ExtractionSourceDocument,
    extraction_id: UUID,
    candidates: list[dict[str, Any]],
    validation: ValidationReport,
    schema_name: str,
) -> int:
    created = 0
    if validation.needs_review or schema_name == "medical_eob":
        upsert_review_task(
            cur,
            document_id=source.document_id,
            extraction_id=extraction_id,
            task_type="extraction_validation",
            reason="Extraction requires review.",
            priority=85 if schema_name == "medical_eob" else 70,
            metadata={"schemaName": schema_name},
        )
        created += 1
    for candidate in candidates:
        if candidate["status"] == "needs_review":
            upsert_review_task(
                cur,
                document_id=source.document_id,
                extraction_id=extraction_id,
                task_type="field_review",
                reason=f"{candidate['field_path']} requires review.",
                priority=75,
                metadata={
                    "fieldPath": candidate["field_path"],
                    "candidateId": str(candidate["id"]),
                },
            )
            created += 1
    return created


def upsert_canonical_field(
    cur: Any,
    *,
    document_id: UUID,
    selected_candidate_id: UUID | None,
    field_path: str,
    ordinal: int,
    value_type: str,
    typed_values: Mapping[str, Any],
    source_kind: str,
    review_status: str,
    evidence: object,
    validation: object,
    accepted_by_user_id: UUID | None,
) -> UUID:
    values = canonical_column_values(typed_values)
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
            values["text_value"],
            values["integer_value"],
            values["numeric_value"],
            values["boolean_value"],
            values["date_value"],
            values["timestamp_value"],
            Jsonb(values["json_value"]),
            values["currency_code"],
            source_kind,
            review_status,
            Jsonb(evidence),
            Jsonb(validation),
            accepted_by_user_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ExtractionRepositoryError("Canonical field upsert failed.")
    return cast(UUID, row["id"])


def canonical_is_human_controlled(
    cur: Any,
    document_id: UUID,
    field_path: str,
    ordinal: int,
) -> bool:
    cur.execute(
        """
        SELECT source_kind, review_status::text AS review_status
        FROM canonical_fields
        WHERE document_id = %s
          AND field_path = %s
          AND ordinal = %s
        """,
        (document_id, field_path, ordinal),
    )
    row = cur.fetchone()
    return bool(row and (row["source_kind"] == "human" or row["review_status"] == "user_corrected"))


def record_canonical_history(
    cur: Any,
    *,
    document_id: UUID,
    canonical_field_id: UUID | None,
    field_path: str | None,
    action: str,
    old_value: object,
    new_value: object,
    actor_user_id: UUID | None,
    reason: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO canonical_fact_history
          (
            document_id, canonical_field_id, field_path, action, old_value_json,
            new_value_json, actor_user_id, reason
          )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        """,
        (
            document_id,
            canonical_field_id,
            field_path,
            action,
            Jsonb(old_value),
            Jsonb(new_value),
            actor_user_id,
            reason,
        ),
    )


def update_document_rollups(cur: Any, document_id: UUID) -> None:
    cur.execute(
        """
        SELECT
          MAX(CASE WHEN field_path IN (
            'receipt.merchant.display_name',
            'invoice.seller.display_name',
            'medical_eob.provider.display_name',
            'medical_eob.payer.display_name'
          ) THEN text_value END) AS counterparty,
          MAX(CASE WHEN field_path IN (
            'receipt.transaction.date_local',
            'invoice.issue_date'
          ) THEN date_value END) AS document_date,
          MAX(CASE WHEN field_path IN (
            'receipt.transaction.total',
            'invoice.total_amount',
            'medical_eob.total_patient_responsibility'
          ) THEN numeric_value END) AS total_amount,
          MAX(currency_code) FILTER (WHERE currency_code IS NOT NULL) AS currency_code
        FROM canonical_fields
        WHERE document_id = %s
          AND review_status IN ('auto_accepted', 'user_confirmed', 'user_corrected')
        """,
        (document_id,),
    )
    row = cur.fetchone() or {}
    cur.execute(
        """
        UPDATE documents
        SET counterparty_display = COALESCE(%s, counterparty_display),
            document_date = COALESCE(%s, document_date),
            review_status = CASE
              WHEN EXISTS (
                SELECT 1 FROM review_tasks
                WHERE document_id = %s AND status IN ('open', 'in_progress')
              ) THEN 'needs_review'::review_status_enum
              WHEN review_status IN ('unreviewed', 'needs_review')
                THEN 'auto_accepted'::review_status_enum
              ELSE review_status
            END,
            updated_at = now()
        WHERE id = %s
        """,
        (row.get("counterparty"), row.get("document_date"), document_id, document_id),
    )
    amount = row.get("total_amount")
    if amount is not None:
        cur.execute(
            """
            DELETE FROM document_amounts
            WHERE document_id = %s
              AND amount_role = 'total'
              AND metadata_json @> %s::jsonb
            """,
            (
                document_id,
                Jsonb({"phase": "phase4", "source": "canonical_fields"}),
            ),
        )
        cur.execute(
            """
            INSERT INTO document_amounts
              (document_id, amount_role, amount, currency_code, metadata_json)
            VALUES (%s, 'total', %s, %s, %s::jsonb)
            """,
            (
                document_id,
                amount,
                row.get("currency_code"),
                Jsonb({"phase": "phase4", "source": "canonical_fields"}),
            ),
        )


def refresh_document_chunk_projection(cur: Any, document_id: UUID) -> None:
    cur.execute("SELECT refresh_document_chunk_projection(%s)", (document_id,))
