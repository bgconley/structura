from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class RelationshipSuggestion:
    from_document_id: UUID
    to_document_id: UUID
    relationship_type: str
    confidence: float
    reason: str
    evidence_text: str


def deterministic_relationship_suggestions(
    rows: list[dict[str, Any]],
    *,
    target_document_id: UUID,
) -> list[RelationshipSuggestion]:
    target = next((row for row in rows if row["id"] == target_document_id), None)
    if not target:
        return []
    suggestions: list[RelationshipSuggestion] = []
    for candidate in rows:
        if candidate["id"] == target_document_id:
            continue
        duplicate = _duplicate_suggestion(target, candidate)
        if duplicate:
            suggestions.append(duplicate)
            continue
        related = _family_contact_suggestion(target, candidate)
        if related:
            suggestions.append(related)
    return _dedupe(suggestions)


def _duplicate_suggestion(
    left: dict[str, Any],
    right: dict[str, Any],
) -> RelationshipSuggestion | None:
    if not left.get("original_sha256") or left.get("original_sha256") != right.get(
        "original_sha256"
    ):
        return None
    return RelationshipSuggestion(
        from_document_id=left["id"],
        to_document_id=right["id"],
        relationship_type="duplicate_of",
        confidence=0.99,
        reason="Exact content fingerprint match.",
        evidence_text=f"SHA-256 {left['original_sha256']} matches {right['title']}.",
    )


def _family_contact_suggestion(
    left: dict[str, Any],
    right: dict[str, Any],
) -> RelationshipSuggestion | None:
    shared_contacts = _shared_contacts(left, right)
    if not shared_contacts:
        return None
    relationship_type = _relationship_type_for_families(str(left["family"]), str(right["family"]))
    if not relationship_type:
        return None
    confidence = (
        0.86 if _near_dates(left.get("document_date"), right.get("document_date")) else 0.78
    )
    contact_text = ", ".join(shared_contacts[:3])
    return RelationshipSuggestion(
        from_document_id=left["id"],
        to_document_id=right["id"],
        relationship_type=relationship_type,
        confidence=confidence,
        reason=f"Shared contact and compatible document families: {contact_text}.",
        evidence_text=f"{left['title']} and {right['title']} share {contact_text}.",
    )


def _relationship_type_for_families(left: str, right: str) -> str | None:
    if left == "invoice" and right == "receipt":
        return "invoice_for"
    if left == "receipt" and right == "invoice":
        return "receipt_for"
    if left == "medical_eob" and right == "medical_bill":
        return "eob_for"
    if left == "medical_bill" and right == "medical_eob":
        return "bill_for"
    if left == "warranty" and right == "receipt":
        return "warranty_for"
    if left == "receipt" and right == "warranty":
        return "receipt_for"
    if left == "legal_contract" and right == "legal_contract":
        return "amendment_to"
    return None


def _shared_contacts(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    left_contacts = {str(item).casefold(): str(item) for item in left.get("contacts") or []}
    shared: list[str] = []
    for item in right.get("contacts") or []:
        key = str(item).casefold()
        if key in left_contacts:
            shared.append(left_contacts[key])
    return shared


def _near_dates(left: object, right: object) -> bool:
    if not isinstance(left, date) or not isinstance(right, date):
        return False
    return abs((left - right).days) <= 45


def _dedupe(suggestions: list[RelationshipSuggestion]) -> list[RelationshipSuggestion]:
    seen: set[tuple[UUID, UUID, str]] = set()
    result: list[RelationshipSuggestion] = []
    for suggestion in suggestions:
        pair = tuple(sorted([suggestion.from_document_id, suggestion.to_document_id]))
        key = (pair[0], pair[1], suggestion.relationship_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(suggestion)
    return result
