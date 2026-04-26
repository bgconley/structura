from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import lib.review.repository as repository
from lib.contracts import CanonicalField, CanonicalFieldWrite, ReviewActionRequest
from lib.documents.access_policy import DocumentAccessContext
from lib.jobs import JobService


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
            evidence = [item.model_dump(by_alias=False) for item in action.evidence_context or []]
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
        else:  # pragma: no cover - Pydantic constrains this.
            raise ReviewServiceError(f"Unsupported review action: {action.action_type}")
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
            evidence=[item.model_dump(by_alias=False) for item in payload.evidence],
            ordinal=payload.ordinal,
            currency=payload.currency,
            selected_candidate_id=payload.selected_candidate_id,
            source_kind=payload.source_kind,
            reason=payload.reason,
        )
        return field

    def _enqueue_rerun(
        self,
        action: ReviewActionRequest,
        *,
        access: DocumentAccessContext,
        actor_user_id: UUID,
    ) -> dict[str, object]:
        target_schema = _target_schema_from_action(action)
        event_id = repository.record_rerun_request(
            document_id=action.document_id,
            access=access,
            actor_user_id=actor_user_id,
            target_schema_name=target_schema,
            reason=action.comment,
        )
        job = JobService().create_job(
            job_type="extract",
            household_id=access.household_id,
            document_id=action.document_id,
            payload={
                "schema_name": "extract_document_job",
                "schema_version": "v1",
                "created_at": datetime.now(UTC).isoformat(),
                "document_id": str(action.document_id),
                "target_schema_name": target_schema,
                "target_schema_version": "v1",
                "requested_by": "user",
                "force_reextract": True,
            },
            priority=45,
            queue_name="extraction",
        )
        return {"ok": True, "reviewEventId": str(event_id), "jobId": str(job.job_id)}


def _candidate_id_from_action(action: ReviewActionRequest) -> UUID:
    metadata = action.metadata or {}
    candidate_id = metadata.get("candidateId") or metadata.get("selectedCandidateId")
    if candidate_id:
        return UUID(str(candidate_id))
    if action.new_value:
        return UUID(str(action.new_value))
    raise ReviewServiceError("confirm_field requires metadata.candidateId.")


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


def _target_schema_from_action(action: ReviewActionRequest) -> str:
    metadata = action.metadata or {}
    schema = metadata.get("targetSchemaName")
    if schema:
        return str(schema)
    value = action.new_value
    if isinstance(value, dict) and value.get("targetSchemaName"):
        return str(value["targetSchemaName"])
    return "receipt"


def _required(value: str | None, name: str) -> str:
    if not value:
        raise ReviewServiceError(f"{name} is required.")
    return value
