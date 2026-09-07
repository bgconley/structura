"""Validated public line authority; persistence metadata never passes through wholesale."""

from typing import Any

from lib.contracts.line_item_authority import (
    LineCandidateDecision,
    LineCanonicalRead,
    LineSlot,
    LineSlotDecision,
    LineSourceAssignment,
)
from lib.documents.line_item_read_model import canonical_line_item_payload
from lib.review.line_items.source_values import public_evidence


def canonical_payload(row: dict[str, Any], *, selected: bool) -> LineCanonicalRead:
    evidence, _ = public_evidence(row.get("evidence_json"))
    # Reuse the actual persisted row/decimal mapping, replacing only potentially
    # extended private evidence and provider validation with explicit public data.
    public = dict(row)
    public["evidence_json"] = [item.model_dump(mode="json", by_alias=True) for item in evidence]
    public["validation_json"] = {"recorded": bool(row.get("validation_json"))}
    payload = canonical_line_item_payload(public)
    payload["selected"] = selected
    return LineCanonicalRead.model_validate(payload)


def slot_decision(row: dict[str, Any]) -> LineSlotDecision:
    return LineSlotDecision.model_validate({key: row[key] for key in LineSlotDecision.model_fields})


def candidate_decision(row: dict[str, Any]) -> LineCandidateDecision:
    return LineCandidateDecision.model_validate(
        {key: row[key] for key in LineCandidateDecision.model_fields}
    )


def assignment_payload(row: dict[str, Any], selected_ids: set[Any]) -> LineSourceAssignment:
    return LineSourceAssignment(
        sourceCandidateId=row["source_candidate_id"],
        state=row["binding_state"],
        canonicalLineItemId=row["canonical_line_item_id"],
        target=LineSlot(lineItemType=row["line_item_type"], ordinal=row["ordinal"])
        if row["binding_state"] == "assigned"
        else None,
        currentlySelected=(row["canonical_line_item_id"], row["source_candidate_id"])
        in selected_ids,
    )
