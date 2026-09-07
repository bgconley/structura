"""Ports for the next writer slice; no SQL implementation or public activation.

Repository implementations own one transaction, revalidate live request authority,
and acquire document -> decision/canonical -> projection -> job locks. They read
preconditions after locks, keep value validation/audit/task closure in that same
transaction, and commit only after projection refresh plus fenced enqueue succeeds.
These declarations alone provide no transaction enforcement or runnable adapter.
"""

from typing import Literal, Protocol
from uuid import UUID

from lib.fact_authority.models import (
    FieldAuthoritySnapshot,
    FieldDecision,
    FieldIdentity,
    FieldPreconditions,
    ManualMetadataValue,
    MetadataDecision,
    ProjectionRevision,
    RevisionExpectation,
)


class HumanAuthorityTransaction(Protocol):
    """Bound to an already authorized document, actor and database transaction.

    Implementations allocate every new decision UUID server-side, preserve review
    history, and never infer an actor or system privilege from missing context.
    No method commits. The surrounding review/organization service owns commit.
    """

    def lock_and_read_field(self, field: FieldIdentity) -> FieldAuthoritySnapshot:
        """Lock document first; fresh read includes absent decision/path-guard rows."""
        ...

    def record_field_decision(
        self,
        *,
        field: FieldIdentity,
        disposition: Literal["confirmed", "corrected", "rejected"],
        expected: FieldPreconditions,
        canonical_field_id: UUID | None,
        review_event_id: UUID,
    ) -> FieldDecision:
        """Recheck both revisions; rejection may reference no canonical fact.

        Acknowledging an active path guard permits this exact human decision;
        it does not resolve the guard for other ordinals or grant model authority.
        """
        ...

    def record_metadata_decision(
        self,
        *,
        value: ManualMetadataValue,
        expected: RevisionExpectation,
        review_event_id: UUID | None,
        audit_event_id: int | None,
    ) -> MetadataDecision:
        """Select explicit classification/date/null-clear with a same-document event."""
        ...

    def refresh_projection_and_enqueue(self) -> ProjectionRevision:
        """Derive accepted facts, rollups and lexical text; fence and enqueue atomically.

        Rejected/protected legacy decisions are never selected as accepted facts.
        Metadata without established ownership is retained as unestablished;
        clearing the last accepted fact clears only a proven owned derived value.
        Any failure rolls back the decision, fact/history, task changes and jobs.
        """
        ...
