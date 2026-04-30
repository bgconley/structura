from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID, uuid4

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.extraction.models import ExtractionSourceDocument
from lib.extraction.repository import load_extraction_source
from lib.jobs import JobService, create_job_with_cursor
from lib.jobs.event_payloads import build_extract_document_job_payload
from lib.semantic_annotations.docling_targets import (
    augment_result_with_docling_structural_targets,
)
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
from lib.semantic_annotations.schema_fit import SchemaFitDecision, schema_fit_for_region
from lib.semantic_annotations.semantic_family import (
    SemanticDocumentFamilyDecision,
    apply_semantic_document_family_decision_with_cursor,
    semantic_document_family_decision,
    source_with_semantic_family,
)
from lib.semantic_annotations.task_routing import corrected_granite_task_for_semantic_type

MAX_GRANITE_TASKS_BY_QUALITY_MODE = {
    "smart": 6,
    "high_quality": 8,
    "rescue": 1,
}
_LINE_ITEM_SEMANTIC_TYPES = {
    "covered_services_line_item_table",
    "invoice_line_item_table",
    "receipt_line_item_table",
    "retail_order_line_item_table",
    "service_record_line_item_table",
    "dispute_transaction_table",
}
_SUMMARY_SEMANTIC_TYPES = {
    "billing_summary",
    "payment_summary",
    "patient_responsibility_summary",
    "receipt_payment_summary",
    "escrow_summary",
    "mortgage_payment_summary",
}
_LOW_VALUE_SEMANTIC_TYPES = {
    "document_header",
    "boilerplate",
    "unsupported_document_region",
    "no_extraction_target",
    "unmatched_region",
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
        qwen8_enabled: bool | None = None,
    ) -> None:
        self.source_loader = source_loader
        self.gateway = gateway or default_semantic_annotation_gateway()
        self.manifest_persister = manifest_persister
        self._use_default_atomic_uow = (
            manifest_persister is persist_semantic_manifest_record and jobs is None
        )
        self.jobs = jobs or JobService()
        self.qwen8_enabled = (
            get_settings().qwen8_enabled if qwen8_enabled is None else qwen8_enabled
        )

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
            qwen8_enabled=self.qwen8_enabled,
        )
        source = self.source_loader(document_id)
        if source.document_id != document_id:
            raise SemanticAnnotationServiceError("Loaded source document ID mismatch.")
        manifest_result = self.gateway.annotate(source, quality_mode=quality_mode)
        manifest_result = augment_result_with_docling_structural_targets(source, manifest_result)
        family_decision = semantic_document_family_decision(source, manifest_result.manifest)
        effective_source = source_with_semantic_family(source, family_decision)
        if self._use_default_atomic_uow:
            return self._persist_and_enqueue_atomically(
                source,
                effective_source,
                manifest_result,
                family_decision,
                requested_by=requested_by,
                allow_8b_rescue=allow_8b_rescue,
                requested_by_user_id=requested_by_user_id,
                user_intent_reason=user_intent_reason,
            )
        persisted = self.manifest_persister(manifest_result.manifest)
        queued_job_ids = self._enqueue_granite_jobs(
            effective_source,
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
        effective_source: ExtractionSourceDocument,
        manifest_result: SemanticAnnotationResult,
        family_decision: SemanticDocumentFamilyDecision,
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
                apply_semantic_document_family_decision_with_cursor(
                    cur,
                    source,
                    family_decision,
                )
                queued_job_ids = self._enqueue_granite_jobs_with_cursor(
                    cur,
                    effective_source,
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
                    metadata={
                        "schema_fit": spec.schema_fit.to_json(),
                        **spec.metadata,
                    },
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
                    metadata={
                        "schema_fit": spec.schema_fit.to_json(),
                        **spec.metadata,
                    },
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
    qwen8_enabled: bool,
) -> None:
    if (quality_mode in {"high_quality", "rescue"} or allow_8b_rescue) and not qwen8_enabled:
        raise SemanticAnnotationServiceError(
            "Qwen3-VL 8B high-quality/rescue semantic pass is disabled."
        )
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
    schema_fit: SchemaFitDecision
    metadata: dict[str, object]


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
    manifest: DocumentSemanticManifest,
) -> SchemaFitDecision:
    document_type_hint = (
        str(manifest.manifest["document_type"])
        if isinstance(manifest.manifest.get("document_type"), str)
        else None
    )
    return schema_fit_for_region(
        source=source,
        region=region,
        document_type_hint=document_type_hint,
    )


def _priority_for_region(region: SemanticRegionAnnotation) -> int:
    if region.priority == "critical":
        base = 28
    elif region.priority == "high":
        base = 32
    elif region.priority == "medium":
        base = 38
    else:
        base = 44

    if region.semantic_type in _LINE_ITEM_SEMANTIC_TYPES:
        base -= 8
    elif region.semantic_type in _SUMMARY_SEMANTIC_TYPES:
        base -= 4
    elif region.semantic_type in _LOW_VALUE_SEMANTIC_TYPES:
        base += 8

    coverage_role = region.metadata.get("coverage_role")
    if coverage_role == "primary":
        base -= 2
    elif coverage_role == "continuation":
        base -= 1
    elif coverage_role in {"supporting", "boilerplate"}:
        base += 4

    if region.metadata.get("source_signal") == "table":
        base -= 2
    if region.metadata.get("requires_full_page_image") is True and (
        region.semantic_type in _LINE_ITEM_SEMANTIC_TYPES
    ):
        base -= 1

    return max(1, base)


def _granite_job_specs(
    source: ExtractionSourceDocument,
    manifest_result: SemanticAnnotationResult,
    persisted: PersistedSemanticManifest,
) -> tuple[GraniteJobSpec, ...]:
    specs: list[GraniteJobSpec] = []
    for ordinal, (region, region_id) in enumerate(_region_pairs(manifest_result, persisted)):
        repaired_region, repair_metadata = _region_for_granite_job(region)
        if not _should_enqueue_granite(repaired_region):
            continue
        schema_fit = _target_schema_for_region(repaired_region, source, manifest_result.manifest)
        if not schema_fit.target_schema:
            continue
        specs.append(
            GraniteJobSpec(
                region=repaired_region,
                region_id=region_id,
                target_schema=schema_fit.target_schema,
                priority=_priority_for_region(repaired_region),
                ordinal=ordinal,
                schema_fit=schema_fit,
                metadata={**repaired_region.metadata, **repair_metadata},
            )
        )
    limit = MAX_GRANITE_TASKS_BY_QUALITY_MODE.get(
        manifest_result.manifest.quality_mode,
        MAX_GRANITE_TASKS_BY_QUALITY_MODE["smart"],
    )
    return tuple(_dedupe_granite_job_specs(sorted(specs, key=_granite_job_sort_key))[:limit])


def _granite_job_sort_key(spec: GraniteJobSpec) -> tuple[object, ...]:
    confidence = spec.region.confidence if spec.region.confidence is not None else 0.0
    return (spec.priority, -confidence, spec.ordinal)


def _dedupe_granite_job_specs(specs: list[GraniteJobSpec]) -> list[GraniteJobSpec]:
    deduped: list[GraniteJobSpec] = []
    seen: set[tuple[object, ...]] = set()
    for spec in specs:
        key = _granite_job_dedupe_key(spec.region)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(spec)
    return deduped


def _granite_job_dedupe_key(region: SemanticRegionAnnotation) -> tuple[object, ...]:
    grounding = region.grounding
    page_level_intent: tuple[str, ...] = ()
    if grounding.element_id is None and grounding.table_id is None:
        page_level_intent = tuple(region.expected_fields)
    return (
        region.semantic_type,
        region.granite_task,
        grounding.kind,
        grounding.page_id,
        grounding.element_id,
        grounding.table_id,
        page_level_intent,
    )


def _region_for_granite_job(
    region: SemanticRegionAnnotation,
) -> tuple[SemanticRegionAnnotation, dict[str, object]]:
    granite_task, repair = corrected_granite_task_for_semantic_type(
        semantic_type=region.semantic_type,
        granite_task=region.granite_task,
    )
    if repair is None:
        return region, {}
    metadata = {**region.metadata, "semantic_task_repair": repair}
    return replace(region, granite_task=granite_task, metadata=metadata), {
        "semantic_task_repair": repair
    }


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
