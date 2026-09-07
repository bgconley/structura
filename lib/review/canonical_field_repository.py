from __future__ import annotations

from typing import Any, Literal, cast
from uuid import UUID

from lib.contracts import CanonicalField
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.extraction.candidate_repository import typed_value_columns
from lib.fact_authority.field_repository import assert_decision_preconditions, record_field_decision
from lib.fact_authority.models import FieldIdentity, RevisionExpectation
from lib.fact_authority.projection_repository import refresh_projection_and_enqueue
from lib.fact_authority.response_mapping import decision_response, projection_response
from lib.review.access import assert_writable
from lib.review.audit_repository import (
    close_field_review_tasks,
    record_history,
    record_review_event,
    update_document_review_status,
)
from lib.review.canonical_value_repository import (
    _canonical_row,
    _typed_value_input,
    _upsert_canonical_row,
)
from lib.review.correction_revision import CorrectionExpectation, assert_canonical_revision
from lib.review.correction_values import CorrectionValueError, correction_storage_value
from lib.review.errors import ReviewRepositoryError
from lib.review.field_decision_result import FieldDecisionResult
from lib.review.mappers import canonical_field_from_row, canonical_value

LEGACY_CORRECTION_EXPECTATION = CorrectionExpectation()
LEGACY_DECISION_EXPECTATION = RevisionExpectation()


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


def correct_field_result(
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
    expectation: CorrectionExpectation = LEGACY_CORRECTION_EXPECTATION,
    decision_expectation: RevisionExpectation = LEGACY_DECISION_EXPECTATION,
    path_guard_expectation: RevisionExpectation = LEGACY_DECISION_EXPECTATION,
) -> FieldDecisionResult:
    _assert_actor(access, actor_user_id)
    storage_value = correction_storage_value(value_type, value, currency)
    if value_type == "money" and isinstance(value, dict):
        currency = str(value["currency"])
    typed = typed_value_columns(value_type, _typed_value_input(value_type, storage_value, currency))
    if currency:
        typed["currency_code"] = currency
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_writable(cur, document_id, access)
            previous = _canonical_row(cur, document_id, field_path, ordinal)
            if previous and previous["value_type"] != value_type:
                raise CorrectionValueError(
                    "A correction must keep the existing field's value type."
                )
            if selected_candidate_id:
                selected = get_field_candidate(
                    cur, document_id=document_id, candidate_id=selected_candidate_id
                )
                if not selected or (
                    selected["field_path"],
                    selected["ordinal"],
                    selected["value_type"],
                ) != (field_path, ordinal, value_type):
                    raise CorrectionValueError("Selected candidate does not match this field.")
            assert_canonical_revision(previous, expectation)
            field = FieldIdentity(document_id=document_id, field_path=field_path, ordinal=ordinal)
            assert_decision_preconditions(cur, field, decision_expectation, path_guard_expectation)
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
            result = _finish_decision(
                cur,
                access,
                field,
                canonical_id,
                event_id,
                actor_user_id,
                "corrected" if source_kind == "human" else "confirmed",
            )
        conn.commit()
    return result


def confirm_candidate_result(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    candidate_id: UUID,
    reason: str | None,
    expected_field_path: str | None = None,
    expected_ordinal: int | None = None,
    expectation: CorrectionExpectation = LEGACY_CORRECTION_EXPECTATION,
    decision_expectation: RevisionExpectation = LEGACY_DECISION_EXPECTATION,
    path_guard_expectation: RevisionExpectation = LEGACY_DECISION_EXPECTATION,
) -> FieldDecisionResult:
    _assert_actor(access, actor_user_id)
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_writable(cur, document_id, access)
            candidate = get_field_candidate(cur, document_id=document_id, candidate_id=candidate_id)
            if not candidate:
                raise ReviewRepositoryError("Candidate not found.")
            if (
                expected_field_path is not None and candidate["field_path"] != expected_field_path
            ) or (expected_ordinal is not None and candidate["ordinal"] != expected_ordinal):
                raise CorrectionValueError("Selected candidate does not match this field.")
            previous = _canonical_row(
                cur, document_id, candidate["field_path"], candidate["ordinal"]
            )
            assert_canonical_revision(previous, expectation)
            field = FieldIdentity(
                document_id=document_id,
                field_path=candidate["field_path"],
                ordinal=candidate["ordinal"],
            )
            assert_decision_preconditions(cur, field, decision_expectation, path_guard_expectation)
            if previous and previous["value_type"] != candidate["value_type"]:
                raise CorrectionValueError(
                    "A confirmation must keep the existing field's value type."
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
                new_value={
                    "valueType": candidate["value_type"],
                    "value": canonical_value(candidate),
                    "currency": candidate.get("currency_code"),
                },
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
                new_value={
                    "valueType": candidate["value_type"],
                    "value": canonical_value(candidate),
                    "currency": candidate.get("currency_code"),
                },
                actor_user_id=actor_user_id,
                reason=reason,
            )
            result = _finish_decision(
                cur, access, field, canonical_id, event_id, actor_user_id, "confirmed"
            )
        conn.commit()
    return result


def reject_field_result(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
    actor_user_id: UUID,
    field_path: str,
    reason: str | None,
    ordinal: int = 1,
    selected_candidate_id: UUID | None = None,
    expectation: CorrectionExpectation = LEGACY_CORRECTION_EXPECTATION,
    decision_expectation: RevisionExpectation = LEGACY_DECISION_EXPECTATION,
    path_guard_expectation: RevisionExpectation = LEGACY_DECISION_EXPECTATION,
) -> FieldDecisionResult:
    _assert_actor(access, actor_user_id)
    with db_connection() as conn:
        with conn.cursor() as cur:
            assert_writable(cur, document_id, access)
            previous = _canonical_row(cur, document_id, field_path, ordinal)
            if selected_candidate_id:
                selected = get_field_candidate(
                    cur, document_id=document_id, candidate_id=selected_candidate_id
                )
                if selected is None or (selected["field_path"], selected["ordinal"]) != (
                    field_path,
                    ordinal,
                ):
                    raise CorrectionValueError("Selected candidate does not match this field.")
            assert_canonical_revision(previous, expectation)
            field = FieldIdentity(document_id=document_id, field_path=field_path, ordinal=ordinal)
            assert_decision_preconditions(cur, field, decision_expectation, path_guard_expectation)
            cur.execute(
                """
                UPDATE field_candidates
                SET status = 'rejected',
                    updated_at = now()
                WHERE document_id = %s
                  AND field_path = %s
                  AND ordinal = %s
                  AND status <> 'rejected'
                """,
                (document_id, field_path, ordinal),
            )
            cur.execute(
                """
                UPDATE canonical_fields
                SET review_status = 'rejected',
                    updated_at = GREATEST(
                      clock_timestamp(), updated_at + interval '1 microsecond'
                    )
                WHERE document_id = %s
                  AND field_path = %s
                  AND ordinal = %s
                """,
                (document_id, field_path, ordinal),
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
            result = _finish_decision(
                cur,
                access,
                field,
                previous["id"] if previous else None,
                event_id,
                actor_user_id,
                "rejected",
            )
        conn.commit()
    return result


def _finish_decision(
    cur: Any,
    access: DocumentAccessContext,
    field: FieldIdentity,
    canonical_id: UUID | None,
    event_id: UUID,
    actor_user_id: UUID,
    disposition: Literal["confirmed", "corrected", "rejected"],
) -> FieldDecisionResult:
    decision = decision_response(
        record_field_decision(
            cur,
            field=field,
            disposition=disposition,
            canonical_field_id=canonical_id,
            review_event_id=event_id,
            actor_user_id=actor_user_id,
        )
    )
    close_field_review_tasks(cur, field.document_id, field.field_path, ordinal=field.ordinal)
    update_document_review_status(cur, field.document_id)
    canonical = None
    if canonical_id:
        cur.execute("SELECT * FROM canonical_fields WHERE id=%s", (canonical_id,))
        canonical = canonical_field_from_row(cur.fetchone())
        canonical.decision = decision
    projection = refresh_projection_and_enqueue(
        cur, document_id=field.document_id, household_id=access.household_id
    )
    return FieldDecisionResult(event_id, decision, canonical, projection_response(projection))


def upsert_human_canonical_field(**kwargs: Any) -> tuple[CanonicalField, UUID]:
    result = correct_field_result(**kwargs)
    if result.canonical is None:
        raise ReviewRepositoryError("Canonical field write failed.")
    return result.canonical, result.event_id


def confirm_candidate(**kwargs: Any) -> UUID:
    return confirm_candidate_result(**kwargs).event_id


def reject_field(**kwargs: Any) -> UUID:
    return reject_field_result(**kwargs).event_id


def _assert_actor(access: DocumentAccessContext, actor_user_id: UUID) -> None:
    if actor_user_id != access.user_id:
        raise ReviewRepositoryError("Document not found.")
