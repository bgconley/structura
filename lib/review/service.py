from __future__ import annotations

from uuid import UUID

import lib.review.repository as repository
from lib.contracts import (
    CanonicalField,
    CanonicalFieldWrite,
    RelationshipDecisionRequest,
    ReviewActionRequest,
)
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.relationships.errors import RelationshipServiceError
from lib.relationships.service import RelationshipService
from lib.search.projection import refresh_projection_and_enqueue_embedding
from lib.semantic_annotations.jobs import enqueue_semantic_annotation_job


class ReviewServiceError(Exception):
    pass


class ReviewService:
    def apply_review_action(
        self,
        action: ReviewActionRequest,
        *,
        access: DocumentAccessContext,
        actor_user_id: UUID,
    ) -> dict[str, object]:
        if action.action_type == "confirm_field":
            candidate_id = _candidate_id_from_action(action)
            event_id = repository.confirm_candidate(
                document_id=action.document_id,
                access=access,
                actor_user_id=actor_user_id,
                candidate_id=candidate_id,
                reason=action.comment,
            )
        elif action.action_type == "correct_field":
            field_path = _required(action.field_path, "fieldPath")
            evidence = _evidence_context_json(action)
            _, event_id = repository.upsert_human_canonical_field(
                document_id=action.document_id,
                access=access,
                actor_user_id=actor_user_id,
                field_path=field_path,
                value_type=_value_type_from_action(action),
                value=action.new_value,
                evidence=evidence,
                currency=_currency_from_action(action),
                reason=action.comment,
            )
        elif action.action_type == "reject_field":
            field_path = _required(action.field_path, "fieldPath")
            event_id = repository.reject_field(
                document_id=action.document_id,
                access=access,
                actor_user_id=actor_user_id,
                field_path=field_path,
                reason=action.comment,
            )
        elif action.action_type == "reclassify_document":
            family, subtype = _classification_from_action(action)
            event_id = repository.record_reclassify(
                document_id=action.document_id,
                access=access,
                actor_user_id=actor_user_id,
                family=family,
                subtype=subtype,
                reason=action.comment,
            )
        elif action.action_type == "rerun_extraction":
            return self._enqueue_rerun(
                action,
                access=access,
                actor_user_id=actor_user_id,
            )
        elif action.action_type == "mark_done":
            event_id = repository.mark_done(
                document_id=action.document_id,
                access=access,
                actor_user_id=actor_user_id,
                review_task_id=action.review_task_id,
                reason=action.comment,
            )
        elif action.action_type == "accept_relationship":
            try:
                relationship = RelationshipService().accept_relationship(
                    _relationship_id_from_action(action),
                    RelationshipDecisionRequest.model_validate({"comment": action.comment}),
                    access=access,
                    actor_user_id=actor_user_id,
                )
            except RelationshipServiceError as exc:
                raise ReviewServiceError(str(exc)) from exc
            return {"ok": True, "relationshipId": str(relationship.id)}
        elif action.action_type == "reject_relationship":
            try:
                relationship = RelationshipService().reject_relationship(
                    _relationship_id_from_action(action),
                    RelationshipDecisionRequest.model_validate({"comment": action.comment}),
                    access=access,
                    actor_user_id=actor_user_id,
                )
            except RelationshipServiceError as exc:
                raise ReviewServiceError(str(exc)) from exc
            return {"ok": True, "relationshipId": str(relationship.id)}
        else:  # pragma: no cover - Pydantic constrains this.
            raise ReviewServiceError(f"Unsupported review action: {action.action_type}")
        if action.action_type in {
            "confirm_field",
            "correct_field",
            "reject_field",
            "reclassify_document",
        }:
            refresh_projection_and_enqueue_embedding(
                document_id=action.document_id,
                household_id=access.household_id,
                force_reembed=False,
            )
        return {"ok": True, "reviewEventId": str(event_id)}

    def write_canonical_field(
        self,
        document_id: UUID,
        payload: CanonicalFieldWrite,
        *,
        access: DocumentAccessContext,
        actor_user_id: UUID,
    ) -> CanonicalField:
        field, _event_id = repository.upsert_human_canonical_field(
            document_id=document_id,
            access=access,
            actor_user_id=actor_user_id,
            field_path=payload.field_path,
            value_type=payload.value_type,
            value=payload.value,
            evidence=[
                item.model_dump(by_alias=False, mode="json", exclude_none=True)
                for item in payload.evidence
            ],
            ordinal=payload.ordinal,
            currency=payload.currency,
            selected_candidate_id=payload.selected_candidate_id,
            source_kind=payload.source_kind,
            reason=payload.reason,
        )
        refresh_projection_and_enqueue_embedding(
            document_id=document_id,
            household_id=access.household_id,
            force_reembed=False,
        )
        return field

    def _enqueue_rerun(
        self,
        action: ReviewActionRequest,
        *,
        access: DocumentAccessContext,
        actor_user_id: UUID,
    ) -> dict[str, object]:
        # Live routing fails closed on broad document-level Granite extraction,
        # so a review rerun re-enters the pipeline at Smart Parse planning:
        # Qwen semantic annotation -> grounded Granite region jobs -> aggregate
        # reconciliation. The requested target schema is recorded as user
        # intent lineage only; it no longer selects a Granite contract.
        requested_schema = _target_schema_from_action(action)
        event_id = repository.record_rerun_request(
            document_id=action.document_id,
            access=access,
            actor_user_id=actor_user_id,
            target_schema_name=requested_schema,
            reason=action.comment,
        )
        with db_connection() as conn:
            with conn.cursor() as cur:
                job_id = enqueue_semantic_annotation_job(
                    cur,
                    document_id=action.document_id,
                    household_id=access.household_id,
                    quality_mode="smart",
                    requested_by="reviewer",
                    requested_by_user_id=actor_user_id,
                    user_intent_reason=action.comment,
                    priority=45,
                    reason="review.rerun_extraction",
                    dedupe_existing=True,
                )
            conn.commit()
        return {"ok": True, "reviewEventId": str(event_id), "jobId": str(job_id)}


def _candidate_id_from_action(action: ReviewActionRequest) -> UUID:
    metadata = action.metadata or {}
    candidate_id = metadata.get("candidateId") or metadata.get("selectedCandidateId")
    if candidate_id:
        return UUID(str(candidate_id))
    if action.new_value:
        return UUID(str(action.new_value))
    raise ReviewServiceError("confirm_field requires metadata.candidateId.")


def _relationship_id_from_action(action: ReviewActionRequest) -> UUID:
    metadata = action.metadata or {}
    relationship_id = metadata.get("relationshipId") or metadata.get("relationship_id")
    if not relationship_id and action.new_value:
        relationship_id = action.new_value
    if relationship_id:
        return UUID(str(relationship_id))
    raise ReviewServiceError("relationship action requires metadata.relationshipId.")


def _evidence_context_json(action: ReviewActionRequest) -> list[dict[str, object]]:
    return [
        item.model_dump(by_alias=False, mode="json", exclude_none=True)
        for item in action.evidence_context or []
    ]


def _value_type_from_action(action: ReviewActionRequest) -> str:
    metadata = action.metadata or {}
    return str(metadata.get("valueType") or "string")


def _currency_from_action(action: ReviewActionRequest) -> str | None:
    metadata = action.metadata or {}
    currency = metadata.get("currency")
    return str(currency) if currency else None


def _classification_from_action(action: ReviewActionRequest) -> tuple[str, str | None]:
    value = action.new_value
    if isinstance(value, dict):
        family = value.get("family")
        subtype = value.get("subtype")
    else:
        family = value
        subtype = None
    if not family:
        raise ReviewServiceError("reclassify_document requires newValue.family.")
    return str(family), str(subtype) if subtype else None


def _target_schema_from_action(action: ReviewActionRequest) -> str | None:
    metadata = action.metadata or {}
    schema = metadata.get("targetSchemaName")
    if schema:
        return str(schema)
    value = action.new_value
    if isinstance(value, dict) and value.get("targetSchemaName"):
        return str(value["targetSchemaName"])
    return None


def _required(value: str | None, name: str) -> str:
    if not value:
        raise ReviewServiceError(f"{name} is required.")
    return value
