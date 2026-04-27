from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.contracts import (
    DocumentDeadline,
    DocumentRelationship,
    RelationshipDecisionRequest,
    RelationshipWrite,
    SmartViewSummary,
    TimelineEvent,
)
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.relationships import repository
from lib.relationships.deadline_status import deadline_status, remind_from
from lib.relationships.errors import RelationshipServiceError
from lib.relationships.suggestions import deterministic_relationship_suggestions

OPEN_DEADLINE_STATUSES = ("open", "due_soon", "overdue", "needs_review")


class RelationshipService:
    def list_relationships(
        self,
        *,
        access: DocumentAccessContext,
        document_id: UUID | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[DocumentRelationship]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                rows = repository.list_relationship_rows(
                    cur,
                    access=access,
                    document_id=document_id,
                    status=status,
                    limit=limit,
                )
        return [_relationship_from_row(row) for row in rows]

    def create_relationship(
        self,
        payload: RelationshipWrite,
        *,
        access: DocumentAccessContext,
        actor_user_id: UUID,
    ) -> DocumentRelationship:
        evidence = [
            item.model_dump(by_alias=True, mode="json", exclude_none=True)
            for item in payload.evidence
        ]
        with db_connection() as conn:
            with conn.cursor() as cur:
                _require_writable_pair(
                    cur,
                    access=access,
                    from_document_id=payload.from_document_id,
                    to_document_id=payload.to_document_id,
                )
                row = repository.upsert_relationship(
                    cur,
                    from_document_id=payload.from_document_id,
                    to_document_id=payload.to_document_id,
                    relationship_type=payload.relationship_type,
                    status="confirmed",
                    source_engine="human",
                    confidence=payload.confidence,
                    evidence=evidence,
                    comment=payload.comment,
                    actor_user_id=actor_user_id,
                )
                repository.record_relationship_audit(
                    cur,
                    event_name="relationship.confirmed",
                    relationship_id=row["id"],
                    document_id=payload.from_document_id,
                    actor_label=str(actor_user_id),
                    payload={
                        "toDocumentId": str(payload.to_document_id),
                        "relationshipType": payload.relationship_type,
                    },
                )
            conn.commit()
        return self._relationship_by_id(
            row["id"],
            access=access,
            document_id=payload.from_document_id,
        )

    def accept_relationship(
        self,
        relationship_id: UUID,
        payload: RelationshipDecisionRequest,
        *,
        access: DocumentAccessContext,
        actor_user_id: UUID,
    ) -> DocumentRelationship:
        return self._decide_relationship(
            relationship_id,
            payload,
            status="confirmed",
            access=access,
            actor_user_id=actor_user_id,
        )

    def reject_relationship(
        self,
        relationship_id: UUID,
        payload: RelationshipDecisionRequest,
        *,
        access: DocumentAccessContext,
        actor_user_id: UUID,
    ) -> DocumentRelationship:
        return self._decide_relationship(
            relationship_id,
            payload,
            status="rejected",
            access=access,
            actor_user_id=actor_user_id,
        )

    def list_deadlines(
        self,
        *,
        access: DocumentAccessContext,
        document_id: UUID | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[DocumentDeadline]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                rows = repository.list_deadline_rows(
                    cur,
                    access=access,
                    document_id=document_id,
                    status=status,
                    limit=limit,
                )
        return [_deadline_from_row(row) for row in rows]

    def timeline(
        self,
        *,
        access: DocumentAccessContext,
        document_id: UUID | None = None,
        contact_id: UUID | None = None,
        limit: int = 200,
    ) -> list[TimelineEvent]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                rows = repository.timeline_rows(
                    cur,
                    access=access,
                    document_id=document_id,
                    contact_id=contact_id,
                    limit=limit,
                )
        return [_timeline_event_from_row(row) for row in rows]

    def smart_views(self, *, access: DocumentAccessContext) -> list[SmartViewSummary]:
        with db_connection() as conn:
            with conn.cursor() as cur:
                counts = repository.smart_view_counts(cur, access=access)
        return [
            SmartViewSummary.model_validate(
                {
                    "key": "open_deadlines",
                    "title": "Open deadlines",
                    "description": (
                        "Documents with unresolved due dates, renewals, or response dates."
                    ),
                    "count": counts["open_deadlines"],
                    "filters": {"hasOpenDeadlines": True},
                }
            ),
            SmartViewSummary.model_validate(
                {
                    "key": "warranties_expiring_soon",
                    "title": "Warranties expiring soon",
                    "description": "Warranty deadlines due in the next 90 days.",
                    "count": counts["warranties_expiring_soon"],
                    "filters": {"deadlineTypes": ["warranty_expiration"], "hasOpenDeadlines": True},
                }
            ),
            SmartViewSummary.model_validate(
                {
                    "key": "renewals",
                    "title": "Renewals",
                    "description": "Documents with open renewal dates.",
                    "count": counts["renewals"],
                    "filters": {"deadlineTypes": ["renewal_date"], "hasOpenDeadlines": True},
                }
            ),
            SmartViewSummary.model_validate(
                {
                    "key": "relationship_suggestions",
                    "title": "Relationship suggestions",
                    "description": "Suggested links that need human confirmation.",
                    "count": counts["relationship_suggestions"],
                    "filters": {"relationshipStatuses": ["suggested"], "hasRelationships": True},
                }
            ),
            SmartViewSummary.model_validate(
                {
                    "key": "unmatched_medical_docs",
                    "title": "Unmatched medical documents",
                    "description": "Medical bills or EOBs without a companion relationship.",
                    "count": counts["unmatched_medical_docs"],
                    "filters": {
                        "families": ["medical_eob", "medical_bill"],
                        "hasRelationships": False,
                    },
                }
            ),
            SmartViewSummary.model_validate(
                {
                    "key": "needs_review",
                    "title": "Needs review",
                    "description": "Documents still waiting for human review.",
                    "count": counts["needs_review"],
                    "filters": {"reviewStatuses": ["needs_review"]},
                }
            ),
            SmartViewSummary.model_validate(
                {
                    "key": "tax_relevant",
                    "title": "Tax relevant",
                    "description": "Tax documents ready for filing workflows.",
                    "count": counts["tax_relevant"],
                    "filters": {"families": ["tax_document"]},
                }
            ),
        ]

    def suggest_for_document(self, document_id: UUID, *, household_id: UUID) -> int:
        with db_connection() as conn:
            with conn.cursor() as cur:
                rows = repository.relationship_context_rows(
                    cur,
                    document_id=document_id,
                    household_id=household_id,
                )
                suggestions = deterministic_relationship_suggestions(
                    rows,
                    target_document_id=document_id,
                )
                for suggestion in suggestions:
                    review_task_id = repository.create_relationship_review_task(
                        cur,
                        document_id=suggestion.from_document_id,
                        relationship_type=suggestion.relationship_type,
                        related_document_id=suggestion.to_document_id,
                        confidence=suggestion.confidence,
                        reason=suggestion.reason,
                    )
                    repository.upsert_relationship(
                        cur,
                        from_document_id=suggestion.from_document_id,
                        to_document_id=suggestion.to_document_id,
                        relationship_type=suggestion.relationship_type,
                        status="suggested",
                        source_engine="system",
                        confidence=suggestion.confidence,
                        evidence=[
                            {
                                "pageNumber": 1,
                                "sourceEngine": "system",
                                "sourceText": suggestion.evidence_text,
                            }
                        ],
                        comment=suggestion.reason,
                        actor_user_id=None,
                        review_task_id=review_task_id,
                    )
            conn.commit()
        return len(suggestions)

    def refresh_deadlines(self, document_id: UUID) -> int:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      cf.field_path,
                      cf.date_value,
                      cf.evidence_json,
                      fc.confidence
                    FROM canonical_fields cf
                    LEFT JOIN field_candidates fc ON fc.id = cf.selected_candidate_id
                    WHERE cf.document_id = %s
                      AND cf.date_value IS NOT NULL
                      AND cf.review_status IN (
                        'auto_accepted',
                        'user_confirmed',
                        'user_corrected'
                      )
                    """,
                    (document_id,),
                )
                rows = cur.fetchall()
                count = 0
                for row in rows:
                    deadline_type = _deadline_type_from_field_path(str(row["field_path"]))
                    if not deadline_type:
                        continue
                    repository.upsert_deadline(
                        cur,
                        document_id=document_id,
                        deadline_type=deadline_type,
                        due_on=row["date_value"],
                        status=deadline_status(
                            due_on=row["date_value"],
                            confidence=row.get("confidence"),
                            evidence=_evidence_list(row.get("evidence_json")),
                        ),
                        remind_from=remind_from(row["date_value"]),
                        confidence=row.get("confidence"),
                        evidence=_evidence_list(row.get("evidence_json")),
                        metadata={"sourceFieldPath": row["field_path"]},
                    )
                    count += 1
            conn.commit()
        return count

    def _decide_relationship(
        self,
        relationship_id: UUID,
        payload: RelationshipDecisionRequest,
        *,
        status: str,
        access: DocumentAccessContext,
        actor_user_id: UUID,
    ) -> DocumentRelationship:
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = repository.decide_relationship(
                    cur,
                    relationship_id=relationship_id,
                    status=status,
                    actor_user_id=actor_user_id,
                    comment=payload.comment,
                    access=access,
                )
                if not row:
                    raise RelationshipServiceError(404, "Relationship not found")
                repository.record_relationship_audit(
                    cur,
                    event_name=f"relationship.{status}",
                    relationship_id=relationship_id,
                    document_id=row["from_document_id"],
                    actor_label=str(actor_user_id),
                    payload={"comment": payload.comment},
                )
            conn.commit()
        return self._relationship_by_id(
            relationship_id,
            access=access,
            document_id=row["from_document_id"],
        )

    def _relationship_by_id(
        self,
        relationship_id: UUID,
        *,
        access: DocumentAccessContext,
        document_id: UUID,
    ) -> DocumentRelationship:
        matches = self.list_relationships(access=access, document_id=document_id, limit=500)
        for item in matches:
            if item.id == relationship_id:
                return item
        raise RelationshipServiceError(404, "Relationship not found")


def _require_writable_pair(
    cur: Any,
    *,
    access: DocumentAccessContext,
    from_document_id: UUID,
    to_document_id: UUID,
) -> None:
    if not repository.document_is_writable(cur, document_id=from_document_id, access=access):
        raise RelationshipServiceError(404, "Source document not found")
    if not repository.document_is_writable(cur, document_id=to_document_id, access=access):
        raise RelationshipServiceError(404, "Related document not found")


def _relationship_from_row(row: dict[str, Any]) -> DocumentRelationship:
    return DocumentRelationship.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "relatedDocumentId": row["related_document_id"],
            "relatedTitle": row["related_title"],
            "relationshipType": row["relationship_type"],
            "status": row["status"],
            "direction": row["direction"],
            "confidence": row.get("confidence"),
            "sourceEngine": row.get("source_engine") or "system",
            "evidence": _evidence_list(row.get("evidence_json")),
            "comment": row.get("comment"),
            "reviewTaskId": row.get("review_task_id"),
            "createdAt": row["created_at"],
        }
    )


def _deadline_from_row(row: dict[str, Any]) -> DocumentDeadline:
    return DocumentDeadline.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "documentTitle": row["document_title"],
            "deadlineType": row["deadline_type"],
            "dueOn": row["due_on"],
            "remindFrom": row.get("remind_from"),
            "status": row["status"],
            "confidence": row.get("confidence"),
            "evidence": _evidence_list(row.get("evidence_json")),
            "metadata": row.get("metadata_json") or {},
        }
    )


def _timeline_event_from_row(row: dict[str, Any]) -> TimelineEvent:
    return TimelineEvent.model_validate(
        {
            "id": row["id"],
            "eventType": row["event_type"],
            "occurredOn": row["occurred_on"],
            "title": row["title"],
            "documentId": row.get("document_id"),
            "documentTitle": row.get("document_title"),
            "relationshipId": row.get("relationship_id"),
            "contactId": row.get("contact_id"),
            "contactName": row.get("contact_name"),
            "deadlineId": row.get("deadline_id"),
            "status": row.get("status"),
            "metadata": row.get("metadata_json") or {},
        }
    )


def _evidence_list(raw: object) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _deadline_type_from_field_path(field_path: str) -> str | None:
    normalized = field_path.casefold()
    if "warranty" in normalized and ("expire" in normalized or "expiration" in normalized):
        return "warranty_expiration"
    if "renewal" in normalized:
        return "renewal_date"
    if "response" in normalized and "deadline" in normalized:
        return "response_deadline"
    if "filing" in normalized and "deadline" in normalized:
        return "filing_deadline"
    if "appointment" in normalized:
        return "appointment_date"
    if "due" in normalized and "date" in normalized:
        return "due_date"
    return None
