from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.extraction.models import ExtractionSourceDocument
from lib.extraction.repository import load_extraction_source
from lib.jobs import JobService, create_job_with_cursor
from lib.jobs.event_payloads import build_extract_document_job_payload
from lib.semantic_annotations.fixture_gateway import FixtureSemanticAnnotationGateway
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    QualityMode,
    SemanticAnnotationResult,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.qwen_gateway import (
    QwenSemanticAnnotationGateway,
    QwenSemanticVisionClient,
)
from lib.semantic_annotations.repository import (
    PersistedSemanticManifest,
    persist_semantic_manifest_record,
    persist_semantic_manifest_with_cursor,
)
from lib.semantic_annotations.target_schema_policy import preferred_target_schema

MAX_GRANITE_TASKS_BY_QUALITY_MODE = {
    "smart": 4,
    "high_quality": 8,
    "rescue": 1,
}


class SemanticAnnotationGateway(Protocol):
    def annotate(
        self,
        source: ExtractionSourceDocument,
        *,
        quality_mode: QualityMode,
    ) -> SemanticAnnotationResult: ...


class JobCreator(Protocol):
    def create_job(self, **kwargs: object) -> object: ...


@dataclass(frozen=True)
class SemanticAnnotationRunResult:
    annotation_id: UUID
    queued_granite_job_ids: tuple[UUID, ...]
    manifest_result: SemanticAnnotationResult


class SemanticAnnotationService:
    def __init__(
        self,
        *,
        source_loader: Callable[[UUID], ExtractionSourceDocument] = load_extraction_source,
        gateway: SemanticAnnotationGateway | None = None,
        manifest_persister: Callable[
            [DocumentSemanticManifest],
            PersistedSemanticManifest,
        ] = persist_semantic_manifest_record,
        jobs: JobCreator | None = None,
    ) -> None:
        self.source_loader = source_loader
        self.gateway = gateway or default_semantic_annotation_gateway()
        self.manifest_persister = manifest_persister
        self._use_default_atomic_uow = (
            manifest_persister is persist_semantic_manifest_record and jobs is None
        )
        self.jobs = jobs or JobService()

    def annotate_document(
        self,
        document_id: UUID,
        *,
        quality_mode: QualityMode = "smart",
        requested_by: str = "system",
        allow_8b_rescue: bool = False,
        requested_by_user_id: UUID | None = None,
        user_intent_reason: str | None = None,
    ) -> SemanticAnnotationRunResult:
        _validate_qwen8b_intent(
            quality_mode=quality_mode,
            requested_by=requested_by,
            allow_8b_rescue=allow_8b_rescue,
        )
        source = self.source_loader(document_id)
        if source.document_id != document_id:
            raise SemanticAnnotationServiceError("Loaded source document ID mismatch.")
        manifest_result = self.gateway.annotate(source, quality_mode=quality_mode)
        if self._use_default_atomic_uow:
            return self._persist_and_enqueue_atomically(
                source,
                manifest_result,
                requested_by=requested_by,
                allow_8b_rescue=allow_8b_rescue,
                requested_by_user_id=requested_by_user_id,
                user_intent_reason=user_intent_reason,
            )
        persisted = self.manifest_persister(manifest_result.manifest)
        queued_job_ids = self._enqueue_granite_jobs(
            source,
            manifest_result,
            persisted,
            requested_by=requested_by,
            allow_8b_rescue=allow_8b_rescue,
            requested_by_user_id=requested_by_user_id,
            user_intent_reason=user_intent_reason,
        )
        return SemanticAnnotationRunResult(
            annotation_id=persisted.annotation_id,
            queued_granite_job_ids=tuple(queued_job_ids),
            manifest_result=manifest_result,
        )

    def _persist_and_enqueue_atomically(
        self,
        source: ExtractionSourceDocument,
        manifest_result: SemanticAnnotationResult,
        *,
        requested_by: str,
        allow_8b_rescue: bool,
        requested_by_user_id: UUID | None,
        user_intent_reason: str | None,
    ) -> SemanticAnnotationRunResult:
        with db_connection() as conn:
            with conn.cursor() as cur:
                persisted = persist_semantic_manifest_with_cursor(
                    cur,
                    manifest_result.manifest,
                )
                queued_job_ids = self._enqueue_granite_jobs_with_cursor(
                    cur,
                    source,
                    manifest_result,
                    persisted,
                    requested_by=requested_by,
                    allow_8b_rescue=allow_8b_rescue,
                    requested_by_user_id=requested_by_user_id,
                    user_intent_reason=user_intent_reason,
                )
            conn.commit()
        return SemanticAnnotationRunResult(
            annotation_id=persisted.annotation_id,
            queued_granite_job_ids=tuple(queued_job_ids),
            manifest_result=manifest_result,
        )

    def _enqueue_granite_jobs(
        self,
        source: ExtractionSourceDocument,
        manifest_result: SemanticAnnotationResult,
        persisted: PersistedSemanticManifest,
        *,
        requested_by: str,
        allow_8b_rescue: bool,
        requested_by_user_id: UUID | None,
        user_intent_reason: str | None,
    ) -> list[UUID]:
        queued: list[UUID] = []
        for spec in _granite_job_specs(source, manifest_result, persisted):
            job_id = uuid4()
            created_job = self.jobs.create_job(
                job_id=job_id,
                job_type="extract",
                household_id=source.household_id,
                document_id=source.document_id,
                payload=build_extract_document_job_payload(
                    job_id=job_id,
                    document_id=source.document_id,
                    target_schema_name=spec.target_schema,
                    target_schema_version="v1",
                    route_profile="docling_plus_granite_structured",
                    requested_by=requested_by,
                    priority=spec.priority,
                    semantic_annotation_id=persisted.annotation_id,
                    semantic_region_id=spec.region_id,
                    semantic_granite_task=spec.region.granite_task,
                    semantic_type=spec.region.semantic_type,
                    semantic_expected_fields=spec.region.expected_fields,
                    semantic_quality_mode=_semantic_quality_mode(
                        manifest_result.manifest.quality_mode
                    ),
                    allow_8b_rescue=allow_8b_rescue,
                    requested_by_user_id=requested_by_user_id,
                    user_intent_reason=user_intent_reason,
                    semantic_rescue=manifest_result.manifest.quality_mode == "rescue",
                ),
                priority=spec.priority,
                queue_name="extraction",
            )
            created_job_id = getattr(created_job, "job_id", None)
            if isinstance(created_job_id, UUID):
                queued.append(created_job_id)
        return queued

    def _enqueue_granite_jobs_with_cursor(
        self,
        cur: object,
        source: ExtractionSourceDocument,
        manifest_result: SemanticAnnotationResult,
        persisted: PersistedSemanticManifest,
        *,
        requested_by: str,
        allow_8b_rescue: bool,
        requested_by_user_id: UUID | None,
        user_intent_reason: str | None,
    ) -> list[UUID]:
        queued: list[UUID] = []
        for spec in _granite_job_specs(source, manifest_result, persisted):
            job_id = uuid4()
            create_job_with_cursor(
                cur,
                job_id=job_id,
                job_type="extract",
                household_id=source.household_id,
                document_id=source.document_id,
                payload=build_extract_document_job_payload(
                    job_id=job_id,
                    document_id=source.document_id,
                    target_schema_name=spec.target_schema,
                    target_schema_version="v1",
                    route_profile="docling_plus_granite_structured",
                    requested_by=requested_by,
                    priority=spec.priority,
                    semantic_annotation_id=persisted.annotation_id,
                    semantic_region_id=spec.region_id,
                    semantic_granite_task=spec.region.granite_task,
                    semantic_type=spec.region.semantic_type,
                    semantic_expected_fields=spec.region.expected_fields,
                    semantic_quality_mode=_semantic_quality_mode(
                        manifest_result.manifest.quality_mode
                    ),
                    allow_8b_rescue=allow_8b_rescue,
                    requested_by_user_id=requested_by_user_id,
                    user_intent_reason=user_intent_reason,
                    semantic_rescue=manifest_result.manifest.quality_mode == "rescue",
                ),
                priority=spec.priority,
                queue_name="extraction",
            )
            queued.append(job_id)
        return queued


class SemanticAnnotationServiceError(Exception):
    pass


def _validate_qwen8b_intent(
    *,
    quality_mode: QualityMode,
    requested_by: str,
    allow_8b_rescue: bool,
) -> None:
    if quality_mode == "high_quality" and requested_by == "system":
        raise SemanticAnnotationServiceError(
            "Qwen3-VL 8B high-quality semantic pass requires explicit user or agent intent."
        )
    if quality_mode == "rescue" and not allow_8b_rescue:
        raise SemanticAnnotationServiceError(
            "Qwen3-VL 8B rescue semantic pass requires persisted user permission."
        )


@dataclass(frozen=True)
class GraniteJobSpec:
    region: SemanticRegionAnnotation
    region_id: UUID
    target_schema: str
    priority: int
    ordinal: int


def default_semantic_annotation_gateway() -> SemanticAnnotationGateway:
    settings = get_settings()
    if settings.model_mode == "fixture":
        return FixtureSemanticAnnotationGateway()
    return QwenSemanticAnnotationGateway(
        client=QwenSemanticVisionClient.from_settings(settings),
    )


def _should_enqueue_granite(region: SemanticRegionAnnotation) -> bool:
    return (
        region.granite_task is not None
        and region.granite_task != "ignore"
        and region.grounding.kind != "unmatched_region"
    )


def _semantic_quality_mode(quality_mode: str) -> str:
    if quality_mode == "high_quality":
        return "high_quality"
    return "smart"


def _target_schema_for_region(
    region: SemanticRegionAnnotation,
    source: ExtractionSourceDocument,
) -> str | None:
    return preferred_target_schema(
        document_family=source.family,
        document_metadata=source.metadata,
        document_type_hint=None,
        semantic_type=region.semantic_type,
        model_target_schema=region.target_schema,
    )


def _priority_for_region(region: SemanticRegionAnnotation) -> int:
    if region.priority == "critical":
        return 28
    if region.priority == "high":
        return 32
    if region.priority == "medium":
        return 38
    return 44


def _granite_job_specs(
    source: ExtractionSourceDocument,
    manifest_result: SemanticAnnotationResult,
    persisted: PersistedSemanticManifest,
) -> tuple[GraniteJobSpec, ...]:
    specs: list[GraniteJobSpec] = []
    for ordinal, (region, region_id) in enumerate(_region_pairs(manifest_result, persisted)):
        if not _should_enqueue_granite(region):
            continue
        target_schema = _target_schema_for_region(region, source)
        if not target_schema:
            continue
        specs.append(
            GraniteJobSpec(
                region=region,
                region_id=region_id,
                target_schema=target_schema,
                priority=_priority_for_region(region),
                ordinal=ordinal,
            )
        )
    limit = MAX_GRANITE_TASKS_BY_QUALITY_MODE.get(
        manifest_result.manifest.quality_mode,
        MAX_GRANITE_TASKS_BY_QUALITY_MODE["smart"],
    )
    return tuple(sorted(specs, key=_granite_job_sort_key)[:limit])


def _granite_job_sort_key(spec: GraniteJobSpec) -> tuple[object, ...]:
    confidence = spec.region.confidence if spec.region.confidence is not None else 0.0
    return (spec.priority, -confidence, spec.ordinal)


def _region_pairs(
    manifest_result: SemanticAnnotationResult,
    persisted: PersistedSemanticManifest,
) -> tuple[tuple[SemanticRegionAnnotation, UUID], ...]:
    regions = tuple(manifest_result.manifest.regions)
    if len(regions) != len(persisted.region_ids):
        raise SemanticAnnotationServiceError(
            "Persisted semantic region count does not match manifest region count."
        )
    return tuple(zip(regions, persisted.region_ids, strict=True))
