from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from lib.config import get_settings
from lib.contracts.registry import ContractRegistry


def build_extract_document_job_payload(
    *,
    job_id: UUID,
    document_id: UUID,
    target_schema_name: str,
    target_schema_version: str = "v1",
    priority: int,
    requested_by: str = "system",
    route_profile: str | None = None,
    force_reextract: bool = False,
    semantic_annotation_id: UUID | None = None,
    semantic_region_id: UUID | None = None,
    semantic_granite_task: str | None = None,
    semantic_type: str | None = None,
    semantic_expected_fields: tuple[str, ...] | list[str] | None = None,
    semantic_quality_mode: str | None = None,
    allow_8b_rescue: bool = False,
    requested_by_user_id: UUID | None = None,
    user_intent_reason: str | None = None,
    semantic_rescue: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _without_none(
        {
            "schema_name": "extract_document_job",
            "schema_version": "v1",
            "job_id": str(job_id),
            "created_at": _now(),
            "attempt": 1,
            "priority": _contract_priority(priority),
            "document_id": str(document_id),
            "target_schema_name": target_schema_name,
            "target_schema_version": target_schema_version,
            "requested_by": requested_by,
            "route_profile": route_profile,
            "force_reextract": force_reextract or None,
            "semantic_annotation_id": (
                str(semantic_annotation_id) if semantic_annotation_id else None
            ),
            "semantic_region_id": str(semantic_region_id) if semantic_region_id else None,
            "semantic_granite_task": semantic_granite_task,
            "semantic_type": semantic_type,
            "semantic_expected_fields": (
                list(semantic_expected_fields) if semantic_expected_fields else None
            ),
            "semantic_quality_mode": semantic_quality_mode,
            "allow_8b_rescue": allow_8b_rescue,
            "requested_by_user_id": (str(requested_by_user_id) if requested_by_user_id else None),
            "user_intent_reason": user_intent_reason,
            "semantic_rescue": semantic_rescue or None,
            "metadata": metadata,
        }
    )
    _registry().validate_event_instance("extract_document_job.v1.schema.json", payload)
    return payload


def build_classify_document_job_payload(
    *,
    job_id: UUID,
    document_id: UUID,
    priority: int,
    requested_by: str = "system",
    force_reclassify: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _without_none(
        {
            "schema_name": "classify_document_job",
            "schema_version": "v1",
            "job_id": str(job_id),
            "created_at": _now(),
            "attempt": 1,
            "priority": _contract_priority(priority),
            "document_id": str(document_id),
            "requested_by": requested_by,
            "force_reclassify": force_reclassify or None,
            "metadata": metadata,
        }
    )
    _registry().validate_event_instance("classify_document_job.v1.schema.json", payload)
    return payload


def build_semantic_annotate_document_job_payload(
    *,
    job_id: UUID,
    document_id: UUID,
    quality_mode: str,
    semantic_quality_mode: str | None = None,
    allow_8b_rescue: bool = False,
    requested_by: str = "system",
    requested_by_user_id: UUID | None = None,
    user_intent_reason: str | None = None,
    reason: str | None = None,
    source_semantic_region_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _without_none(
        {
            "schema_name": "semantic_annotate_document_job",
            "schema_version": "v1",
            "job_id": str(job_id),
            "created_at": _now(),
            "document_id": str(document_id),
            "quality_mode": quality_mode,
            "semantic_quality_mode": semantic_quality_mode or _semantic_quality_mode(quality_mode),
            "allow_8b_rescue": allow_8b_rescue,
            "requested_by": requested_by,
            "requested_by_user_id": (str(requested_by_user_id) if requested_by_user_id else None),
            "user_intent_reason": user_intent_reason,
            "reason": reason,
            "source_semantic_region_id": (
                str(source_semantic_region_id) if source_semantic_region_id else None
            ),
            "metadata": metadata,
        }
    )
    _registry().validate_event_instance(
        "semantic_annotate_document_job.v1.schema.json",
        payload,
    )
    return payload


def _contract_priority(pipeline_priority: int) -> int:
    return max(1, min(10, round(pipeline_priority / 10)))


def _semantic_quality_mode(quality_mode: str) -> str:
    if quality_mode == "high_quality":
        return "high_quality"
    return "smart"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _without_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


@lru_cache
def _registry() -> ContractRegistry:
    return ContractRegistry.from_settings(get_settings())
