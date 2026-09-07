"""Committed field-decision output shared by review actions and correction POSTs."""

from dataclasses import dataclass
from uuid import UUID

from lib.contracts import CanonicalField, FieldDecision, FieldProjectionRevision


@dataclass(frozen=True)
class FieldDecisionResult:
    event_id: UUID
    decision: FieldDecision
    canonical: CanonicalField | None
    projection: FieldProjectionRevision

    def response(self) -> dict[str, object]:
        return {
            "ok": True,
            "reviewEventId": str(self.event_id),
            "decision": self.decision.model_dump(by_alias=True, mode="json"),
            "canonical": self.canonical.model_dump(by_alias=True, mode="json")
            if self.canonical
            else None,
            "projection": self.projection.model_dump(by_alias=True, mode="json"),
        }
