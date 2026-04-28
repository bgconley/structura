from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.extraction.classification import TARGET_EXTRACTION_SCHEMAS
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
    ) -> SemanticAnnotationRunResult:
        source = self.source_loader(document_id)
        if source.document_id != document_id:
            raise SemanticAnnotationServiceError("Loaded source document ID mismatch.")
        manifest_result = self.gateway.annotate(source, quality_mode=quality_mode)
        if self._use_default_atomic_uow:
            return self._persist_and_enqueue_atomically(
                source,
                manifest_result,
                requested_by=requested_by,
            )
        persisted = self.manifest_persister(manifest_result.manifest)
        queued_job_ids = self._enqueue_granite_jobs(
            source,
            manifest_result,
            persisted,
            requested_by=requested_by,
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
    ) -> list[UUID]:
        queued: list[UUID] = []
        region_pairs = _region_pairs(manifest_result, persisted)
        for region, region_id in region_pairs:
            if not _should_enqueue_granite(region):
                continue
            target_schema = _target_schema_for_region(region, source)
            if not target_schema:
                continue
            priority = _priority_for_region(region)
            job_id = uuid4()
            job = self.jobs.create_job(
                job_id=job_id,
                job_type="extract",
                household_id=source.household_id,
                document_id=source.document_id,
                payload=build_extract_document_job_payload(
                    job_id=job_id,
                    document_id=source.document_id,
                    target_schema_name=target_schema,
                    target_schema_version="v1",
                    route_profile="docling_plus_granite_structured",
                    requested_by=requested_by,
                    priority=priority,
                    semantic_annotation_id=persisted.annotation_id,
                    semantic_region_id=region_id,
                    semantic_granite_task=region.granite_task,
                    semantic_type=region.semantic_type,
                    semantic_expected_fields=region.expected_fields,
                    semantic_rescue=manifest_result.manifest.quality_mode == "rescue",
                ),
                priority=priority,
                queue_name="extraction",
            )
            job_id = getattr(job, "job_id", None)
            if isinstance(job_id, UUID):
                queued.append(job_id)
        return queued

    def _enqueue_granite_jobs_with_cursor(
        self,
        cur: object,
        source: ExtractionSourceDocument,
        manifest_result: SemanticAnnotationResult,
        persisted: PersistedSemanticManifest,
        *,
        requested_by: str,
    ) -> list[UUID]:
        queued: list[UUID] = []
        for region, region_id in _region_pairs(manifest_result, persisted):
            if not _should_enqueue_granite(region):
                continue
            target_schema = _target_schema_for_region(region, source)
            if not target_schema:
                continue
            priority = _priority_for_region(region)
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
                    target_schema_name=target_schema,
                    target_schema_version="v1",
                    route_profile="docling_plus_granite_structured",
                    requested_by=requested_by,
                    priority=priority,
                    semantic_annotation_id=persisted.annotation_id,
                    semantic_region_id=region_id,
                    semantic_granite_task=region.granite_task,
                    semantic_type=region.semantic_type,
                    semantic_expected_fields=region.expected_fields,
                    semantic_rescue=manifest_result.manifest.quality_mode == "rescue",
                ),
                priority=priority,
                queue_name="extraction",
            )
            queued.append(job_id)
        return queued


class SemanticAnnotationServiceError(Exception):
    pass


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


def _target_schema_for_region(
    region: SemanticRegionAnnotation,
    source: ExtractionSourceDocument,
) -> str | None:
    if region.target_schema:
        return region.target_schema
    if source.family in TARGET_EXTRACTION_SCHEMAS:
        return source.family
    return None


def _priority_for_region(region: SemanticRegionAnnotation) -> int:
    if region.priority == "critical":
        return 28
    if region.priority == "high":
        return 32
    if region.priority == "medium":
        return 38
    return 44


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
