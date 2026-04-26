from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lib.contracts import CanonicalField, FieldCandidate, ReviewTask
from lib.extraction.candidate_repository import value_from_candidate_row


def review_task_from_row(row: Mapping[str, Any]) -> ReviewTask:
    metadata = row.get("metadata_json") or {}
    return ReviewTask.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "taskType": row["task_type"],
            "status": row["status"],
            "priority": row["priority"],
            "pageNumber": metadata.get("pageNumber"),
            "fieldPath": metadata.get("fieldPath"),
            "rationale": row.get("reason"),
        }
    )


def field_candidate_from_row(row: Mapping[str, Any]) -> FieldCandidate:
    return FieldCandidate.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "extractionId": row.get("extraction_id"),
            "fieldPath": row["field_path"],
            "ordinal": row["ordinal"],
            "valueType": row["value_type"],
            "value": value_from_candidate_row(row),
            "normalizedValue": value_from_candidate_row(row),
            "currency": row.get("currency_code"),
            "confidence": row.get("confidence"),
            "authorityWeight": row.get("authority_weight"),
            "sourceEngine": row["source_engine"],
            "evidence": row.get("evidence_json") or [],
            "validation": row.get("validation_json") or {},
            "status": row.get("status"),
        }
    )


def canonical_field_from_row(row: Mapping[str, Any]) -> CanonicalField:
    return CanonicalField.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "selectedCandidateId": row.get("selected_candidate_id"),
            "fieldPath": row["field_path"],
            "ordinal": row["ordinal"],
            "valueType": row["value_type"],
            "value": canonical_value(row),
            "currency": row.get("currency_code"),
            "sourceKind": row["source_kind"],
            "reviewStatus": row["review_status"],
            "evidence": row.get("evidence_json") or [],
            "validation": row.get("validation_json") or {},
            "acceptedAt": row.get("accepted_at"),
        }
    )


def canonical_value(row: Mapping[str, Any] | None) -> Any:
    if not row:
        return None
    return value_from_candidate_row(row)
