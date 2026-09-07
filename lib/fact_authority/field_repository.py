"""Current field decisions, serialized by the owning document before any lookup."""

from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID

from lib.extraction.canonical_authority import canonical_field_is_human_controlled
from lib.fact_authority.models import (
    CanonicalRevision,
    FieldAuthoritySnapshot,
    FieldDecision,
    FieldIdentity,
    FieldPathGuard,
    RevisionExpectation,
)
from lib.fact_authority.preconditions import check_decision_revision


def read_field_authority(cur: Any, field: FieldIdentity) -> FieldAuthoritySnapshot:
    cur.execute(
        "SELECT id,updated_at,source_kind,review_status,accepted_by_user_id "
        "FROM canonical_fields WHERE document_id=%s AND field_path=%s AND ordinal=%s",
        (field.document_id, field.field_path, field.ordinal),
    )
    row = cur.fetchone()
    canonical = (
        CanonicalRevision(
            id=row["id"],
            updated_at=row["updated_at"],
            review_status=row["review_status"],
            human_controlled=canonical_field_is_human_controlled(row),
        )
        if row
        else None
    )
    cur.execute(
        "SELECT * FROM canonical_field_decisions "
        "WHERE document_id=%s AND field_path=%s AND ordinal=%s FOR UPDATE",
        (field.document_id, field.field_path, field.ordinal),
    )
    decision = cur.fetchone()
    cur.execute(
        "SELECT * FROM canonical_field_path_guards "
        "WHERE document_id=%s AND field_path=%s FOR UPDATE",
        (field.document_id, field.field_path),
    )
    guard = cur.fetchone()
    return FieldAuthoritySnapshot(
        field=field,
        canonical=canonical,
        decision=decision_from_row(decision) if decision else None,
        path_guard=guard_from_row(guard) if guard else None,
    )


def assert_decision_preconditions(
    cur: Any, field: FieldIdentity, decision: RevisionExpectation, path_guard: RevisionExpectation
) -> None:
    state = read_field_authority(cur, field)
    check_decision_revision(state.decision.revision if state.decision else None, decision)
    active_guard = (
        state.path_guard if state.path_guard and state.path_guard.status == "active" else None
    )
    check_decision_revision(active_guard.revision if active_guard else None, path_guard)


def record_field_decision(
    cur: Any,
    *,
    field: FieldIdentity,
    disposition: Literal["confirmed", "corrected", "rejected"],
    canonical_field_id: UUID | None,
    review_event_id: UUID,
    actor_user_id: UUID,
) -> FieldDecision:
    cur.execute(
        """INSERT INTO canonical_field_decisions
        (document_id,field_path,ordinal,disposition,origin,canonical_field_id,review_event_id,
         actor_user_id,decided_at)
        VALUES (%s,%s,%s,%s,'live_review',%s,%s,%s,clock_timestamp())
        ON CONFLICT (document_id,field_path,ordinal) DO UPDATE SET
          disposition=EXCLUDED.disposition,origin='live_review',revision=gen_random_uuid(),
          canonical_field_id=EXCLUDED.canonical_field_id,review_event_id=EXCLUDED.review_event_id,
          actor_user_id=EXCLUDED.actor_user_id,decided_at=EXCLUDED.decided_at,
          recorded_at=GREATEST(clock_timestamp(),
            canonical_field_decisions.recorded_at+interval '1 microsecond')
        RETURNING *""",
        (
            field.document_id,
            field.field_path,
            field.ordinal,
            disposition,
            canonical_field_id,
            review_event_id,
            actor_user_id,
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("Field decision persistence failed.")
    return decision_from_row(row)


def decision_from_row(row: Mapping[str, Any]) -> FieldDecision:
    return FieldDecision(
        id=row["id"],
        field=FieldIdentity(
            document_id=row["document_id"], field_path=row["field_path"], ordinal=row["ordinal"]
        ),
        revision=row["revision"],
        disposition=row["disposition"],
        origin=row["origin"],
        canonical_field_id=row["canonical_field_id"],
        review_event_id=row["review_event_id"],
        actor_user_id=row["actor_user_id"],
        decided_at=row["decided_at"],
        recorded_at=row["recorded_at"],
    )


def guard_from_row(row: Mapping[str, Any]) -> FieldPathGuard:
    return FieldPathGuard(**{name: row[name] for name in FieldPathGuard.model_fields})
