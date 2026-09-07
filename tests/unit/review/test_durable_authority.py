from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lib.fact_authority.models import (
    CanonicalExpectation,
    CanonicalRevision,
    FieldAuthoritySnapshot,
    FieldDecision,
    FieldIdentity,
    FieldPathGuard,
    FieldPreconditions,
    ManualClassification,
    ManualDocumentDate,
    ProjectionRevision,
    RevisionExpectation,
)
from lib.fact_authority.preconditions import (
    AuthorityRevisionConflict,
    automatic_promotion_is_protected,
    canonical_is_selected_accepted,
    check_field_preconditions,
)


def state(disposition=None, *, canonical=True, human=False, guard=False):
    field = FieldIdentity(document_id=uuid4(), field_path="invoice.total_amount", ordinal=2)
    row = (
        CanonicalRevision(
            id=uuid4(),
            updated_at=datetime.now(UTC),
            human_controlled=human,
            review_status="user_confirmed" if human else "auto_accepted",
        )
        if canonical
        else None
    )
    decision = (
        FieldDecision(
            id=uuid4(),
            field=field,
            revision=uuid4(),
            disposition=disposition,
            origin="legacy_current_field",
            canonical_field_id=row.id if row else None,
            review_event_id=None,
            actor_user_id=None,
            decided_at=None,
            recorded_at=datetime.now(UTC),
        )
        if disposition
        else None
    )
    path_guard = (
        FieldPathGuard(
            id=uuid4(),
            document_id=field.document_id,
            field_path=field.field_path,
            revision=uuid4(),
            status="active",
            review_event_id=None,
            actor_user_id=None,
        )
        if guard
        else None
    )
    return FieldAuthoritySnapshot(
        field=field, canonical=row, decision=decision, path_guard=path_guard
    )


def current_expectation(snapshot):
    return FieldPreconditions(
        canonical=CanonicalExpectation(
            supplied=True, updated_at=snapshot.canonical.updated_at if snapshot.canonical else None
        ),
        decision=RevisionExpectation(
            supplied=True, revision=snapshot.decision.revision if snapshot.decision else None
        ),
        path_guard=RevisionExpectation(
            supplied=True, revision=snapshot.path_guard.revision if snapshot.path_guard else None
        ),
    )


@pytest.mark.parametrize("canonical", [False, True])
@pytest.mark.parametrize(
    "expectation",
    [
        FieldPreconditions(),
        FieldPreconditions(
            decision=RevisionExpectation(supplied=True),
            canonical=CanonicalExpectation(supplied=True),
        ),
    ],
)
def test_missing_or_absent_decision_cannot_replace_unseen_rejection(canonical, expectation):
    snapshot = state("rejected", canonical=canonical)
    with pytest.raises(AuthorityRevisionConflict):
        check_field_preconditions(snapshot, expectation)
    check_field_preconditions(snapshot, current_expectation(snapshot))
    assert automatic_promotion_is_protected(snapshot)
    assert not canonical_is_selected_accepted(snapshot)


def test_first_decision_on_machine_fact_preserves_legacy_client_compatibility():
    snapshot = state()
    check_field_preconditions(snapshot, FieldPreconditions())
    assert not automatic_promotion_is_protected(snapshot)
    assert canonical_is_selected_accepted(snapshot)


@pytest.mark.parametrize("changed", ["decision", "canonical", "path_guard"])
def test_three_independent_expectations_do_not_substitute_for_one_another(changed):
    snapshot = state("confirmed", human=True, guard=True)
    expected = current_expectation(snapshot)
    if changed == "canonical":
        stale = CanonicalExpectation(
            supplied=True, updated_at=datetime.now(UTC) - timedelta(days=1)
        )
    else:
        stale = RevisionExpectation(supplied=True, revision=uuid4())
    with pytest.raises(AuthorityRevisionConflict):
        check_field_preconditions(snapshot, expected.model_copy(update={changed: stale}))
    check_field_preconditions(snapshot, expected)


def test_path_guard_blocks_all_ordinals_but_current_human_decision_can_be_accepted():
    ambiguous = state(guard=True)
    assert not canonical_is_selected_accepted(ambiguous)
    with pytest.raises(AuthorityRevisionConflict):
        check_field_preconditions(ambiguous, FieldPreconditions())
    acknowledged = state("confirmed", human=True, guard=True)
    check_field_preconditions(acknowledged, current_expectation(acknowledged))
    assert canonical_is_selected_accepted(acknowledged)
    assert automatic_promotion_is_protected(acknowledged)
    assert acknowledged.path_guard.status == "active"


@pytest.mark.parametrize("disposition", ["rejected", "protected_legacy"])
def test_rejected_or_unknown_human_authority_never_uses_stale_accepted_column(disposition):
    snapshot = state(disposition, human=True)
    assert not canonical_is_selected_accepted(snapshot)
    assert automatic_promotion_is_protected(snapshot)


def test_snapshots_are_immutable_and_cannot_bind_another_field_or_ordinal():
    snapshot = state("confirmed")
    with pytest.raises(ValidationError):
        snapshot.decision.disposition = "rejected"
    with pytest.raises(ValidationError, match="exact field"):
        FieldAuthoritySnapshot(
            field=snapshot.field.model_copy(update={"ordinal": 1}),
            canonical=snapshot.canonical,
            decision=snapshot.decision,
            path_guard=None,
        )


@pytest.mark.parametrize("value", [True, 0, "2026-02-30", "20260907", "2026-09-07T00:00:00Z"])
def test_manual_date_rejects_non_calendar_values(value):
    with pytest.raises((ValidationError, ValueError)):
        ManualDocumentDate(value=value)


def test_manual_null_is_explicit_and_classification_is_a_complete_pair():
    assert ManualDocumentDate(value=None).model_dump(mode="json")["value"] is None
    with pytest.raises(ValidationError):
        ManualDocumentDate()
    with pytest.raises(ValidationError):
        ManualClassification(family="invoice")
    assert ManualClassification(family="invoice", subtype=None).subtype is None


def test_unestablished_revision_does_not_claim_verified_empty_facts():
    snapshot = ProjectionRevision(
        document_id=uuid4(),
        state="unestablished",
        accepted_fact_revision=0,
        projection_revision=0,
        accepted_facts_sha256=None,
        indexed_metadata_sha256=None,
    )
    assert snapshot.verified_fact_revision is None
    with pytest.raises(ValidationError):
        ProjectionRevision.model_validate(snapshot.model_dump() | {"state": "current"})
    current = ProjectionRevision.model_validate(
        snapshot.model_dump()
        | {
            "state": "current",
            "accepted_fact_revision": 1,
            "projection_revision": 1,
            "accepted_facts_sha256": "a" * 64,
            "indexed_metadata_sha256": "b" * 64,
        }
    )
    assert current.verified_fact_revision == 1
