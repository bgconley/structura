"""Concurrency policy only; authentication and DB serialization remain repository duties."""

from uuid import UUID

from lib.fact_authority.models import (
    FieldAuthoritySnapshot,
    FieldPreconditions,
    RevisionExpectation,
)


class AuthorityRevisionConflict(Exception):
    """The request did not acknowledge current human authority or canonical state."""


def check_decision_revision(current: UUID | None, expected: RevisionExpectation) -> None:
    if (not expected.supplied and current is not None) or (
        expected.supplied and expected.revision != current
    ):
        raise AuthorityRevisionConflict("Reload the current human decision before changing it.")


def check_field_preconditions(
    snapshot: FieldAuthoritySnapshot, expected: FieldPreconditions
) -> None:
    check_decision_revision(
        snapshot.decision.revision if snapshot.decision else None, expected.decision
    )
    active_guard = (
        snapshot.path_guard
        if (snapshot.path_guard and snapshot.path_guard.status == "active")
        else None
    )
    check_decision_revision(active_guard.revision if active_guard else None, expected.path_guard)
    canonical = snapshot.canonical
    if expected.canonical.supplied:
        current = canonical.updated_at if canonical else None
        matches = current == expected.canonical.updated_at
    else:
        matches = not (canonical and canonical.human_controlled)
    if not matches:
        raise AuthorityRevisionConflict("Reload the current canonical field before changing it.")


def automatic_promotion_is_protected(snapshot: FieldAuthoritySnapshot) -> bool:
    """A validator's acceptance alone never establishes human authority."""
    return bool(
        snapshot.decision
        or (snapshot.path_guard and snapshot.path_guard.status == "active")
        or (snapshot.canonical and snapshot.canonical.human_controlled)
    )


def canonical_is_selected_accepted(snapshot: FieldAuthoritySnapshot) -> bool:
    """Decisions gate acceptance independently of stale canonical status columns."""
    canonical = snapshot.canonical
    if canonical is None or canonical.review_status not in {
        "auto_accepted",
        "user_confirmed",
        "user_corrected",
    }:
        return False
    if snapshot.decision:
        return (
            snapshot.decision.disposition in {"confirmed", "corrected"}
            and snapshot.decision.canonical_field_id == canonical.id
        )
    return not (snapshot.path_guard and snapshot.path_guard.status == "active")
