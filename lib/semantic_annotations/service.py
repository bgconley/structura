from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID, uuid4

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.extraction.contract_registry import (
    CONTRACT_REGISTRY_VERSION,
    resolve_model_output_contract,
)
from lib.extraction.granite_budgets import granite_budget_for_task
from lib.extraction.models import ExtractionSourceDocument
from lib.extraction.repository import load_extraction_source
from lib.jobs import JobService, create_job_with_cursor
from lib.jobs.event_payloads import build_extract_document_job_payload
from lib.model_runtime.reliability_versions import REGION_ENVELOPE_VERSION
from lib.semantic_annotations.docling_audit import build_docling_audit
from lib.semantic_annotations.docling_targets import (
    augment_result_with_docling_structural_targets,
)
from lib.semantic_annotations.extraction_plan import (
    GraniteExtractionPlan,
    GraniteJobSpec,
    plan_granite_jobs,
)
from lib.semantic_annotations.extraction_plan_repository import (
    persist_extraction_plan_with_cursor,
)
from lib.semantic_annotations.fixture_gateway import FixtureSemanticAnnotationGateway
from lib.semantic_annotations.manifest_normalization import normalize_result_for_planning
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    QualityMode,
    SemanticAnnotationResult,
    SemanticExtractionTask,
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
_OBSERVATION_DOCUMENT_TYPES = {
    "real_estate_title",
    "mortgage_escrow_statement",
    "financial_dispute_form",
}
_GENERIC_DOCUMENT_TYPES = {
    "document_observation",
    "generic",
    "generic_form",
    "unsupported_document",
    "no_extraction_target",
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
        _validate_active_semantic_mode(
            quality_mode=quality_mode,
            allow_8b_rescue=allow_8b_rescue,
        )
        source = self.source_loader(document_id)
        if source.document_id != document_id:
            raise SemanticAnnotationServiceError("Loaded source document ID mismatch.")
        manifest_result = self.gateway.annotate(source, quality_mode=quality_mode)
        manifest_result = augment_result_with_docling_structural_targets(source, manifest_result)
        manifest_result = normalize_result_for_planning(source, manifest_result)
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
        plan = _granite_extraction_plan(source, manifest_result, persisted)
        run_id = _run_id_from_source(source)
        for spec in plan.selected:
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
                    model_output_schema_name=spec.model_output_schema_name,
                    canonical_target_schema=spec.canonical_target_schema,
                    compatibility_mode=spec.compatibility_mode,
                    extractor_backend=spec.extractor_backend,
                    contract_resolution_reason=spec.contract_resolution_reason,
                    region_envelope_version=REGION_ENVELOPE_VERSION,
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
                        **({"run_id": run_id} if run_id else {}),
                    },
                ),
                priority=spec.priority,
                queue_name="extraction",
                max_attempts=_max_attempts_for_granite_spec(
                    spec,
                    document_id=source.document_id,
                    annotation_id=persisted.annotation_id,
                ),
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
        plan = _granite_extraction_plan(source, manifest_result, persisted)
        run_id = _run_id_from_source(source)
        persisted_plan = persist_extraction_plan_with_cursor(
            cur,
            document_id=source.document_id,
            semantic_annotation_id=persisted.annotation_id,
            manifest_result=manifest_result,
            plan=plan,
            run_id=run_id,
        )
        for spec in plan.selected:
            plan_task_id = persisted_plan.selected_task_ids.get(spec.region_id)
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
                    plan_id=persisted_plan.plan_id,
                    plan_task_id=plan_task_id,
                    model_output_schema_name=spec.model_output_schema_name,
                    canonical_target_schema=spec.canonical_target_schema,
                    compatibility_mode=spec.compatibility_mode,
                    extractor_backend=spec.extractor_backend,
                    contract_resolution_reason=spec.contract_resolution_reason,
                    region_envelope_version=REGION_ENVELOPE_VERSION,
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
                        **({"run_id": run_id} if run_id else {}),
                    },
                ),
                priority=spec.priority,
                queue_name="extraction",
                max_attempts=_max_attempts_for_granite_spec(
                    spec,
                    document_id=source.document_id,
                    annotation_id=persisted.annotation_id,
                ),
            )
            queued.append(job_id)
        return queued


class SemanticAnnotationServiceError(Exception):
    pass


def _validate_active_semantic_mode(
    *,
    quality_mode: QualityMode,
    allow_8b_rescue: bool,
) -> None:
    if quality_mode in {"high_quality", "rescue"} or allow_8b_rescue:
        raise SemanticAnnotationServiceError(
            "Separate high-quality/rescue semantic passes have been removed from "
            "the active runtime. Smart Parse already uses Qwen3-VL-8B FP8."
        )


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


def _run_id_from_source(source: ExtractionSourceDocument) -> str | None:
    hints = source.metadata.get("hints")
    if not isinstance(hints, dict):
        return None
    value = hints.get("runId") or hints.get("run_id")
    if value in (None, ""):
        return None
    return str(value)


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


def _granite_extraction_plan(
    source: ExtractionSourceDocument,
    manifest_result: SemanticAnnotationResult,
    persisted: PersistedSemanticManifest,
) -> GraniteExtractionPlan:
    specs: list[GraniteJobSpec] = []
    for ordinal, (region, region_id) in enumerate(_region_pairs(manifest_result, persisted)):
        repaired_region, repair_metadata = _region_for_granite_job(region)
        if not _should_enqueue_granite(repaired_region):
            continue
        schema_fit = _target_schema_for_region(repaired_region, source, manifest_result.manifest)
        if not schema_fit.target_schema:
            continue
        resolved_document_type = _resolved_document_type_for_plan(
            source=source,
            manifest=manifest_result.manifest,
            region=repaired_region,
            target_schema=schema_fit.target_schema,
        )
        contract = resolve_model_output_contract(
            resolved_document_type=resolved_document_type,
            semantic_type=repaired_region.semantic_type,
            granite_task=repaired_region.granite_task or "",
            target_schema=schema_fit.target_schema,
            allow_generic_fallback=schema_fit.target_schema == "document_observation",
        )
        metadata = {
            **repaired_region.metadata,
            **repair_metadata,
            "resolved_document_type": resolved_document_type,
            "semantic_document_type": _semantic_document_type(manifest_result.manifest),
            "canonical_target_schema": contract.canonical_target_schema,
            "model_output_schema_name": contract.schema_name,
            "contract_resolution_reason": contract.reason,
            "compatibility_mode": contract.compatibility_mode,
            "contract_registry_version": CONTRACT_REGISTRY_VERSION,
            "document_observation_review_only": schema_fit.target_schema == "document_observation",
        }
        specs.append(
            GraniteJobSpec(
                region=repaired_region,
                region_id=region_id,
                target_schema=schema_fit.target_schema,
                canonical_target_schema=contract.canonical_target_schema
                or schema_fit.target_schema,
                model_output_schema_name=contract.schema_name or "",
                contract_resolution_reason=contract.reason,
                compatibility_mode=contract.compatibility_mode,
                extractor_backend="granite_region",
                priority=_priority_for_region(repaired_region),
                ordinal=ordinal,
                schema_fit=schema_fit,
                metadata=metadata,
            )
        )
    return plan_granite_jobs(
        specs,
        quality_mode=manifest_result.manifest.quality_mode,
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


def _max_attempts_for_granite_spec(
    spec: GraniteJobSpec,
    *,
    document_id: UUID,
    annotation_id: UUID,
) -> int:
    if spec.region.granite_task is None:
        return 1
    task = SemanticExtractionTask(
        region_id=spec.region_id,
        annotation_id=annotation_id,
        document_id=document_id,
        semantic_type=spec.region.semantic_type,
        granite_task=spec.region.granite_task,
        target_schema=spec.region.target_schema or spec.target_schema,
        expected_fields=spec.region.expected_fields,
        grounding=spec.region.grounding,
        reason=spec.region.reason,
        confidence=spec.region.confidence,
        metadata=spec.region.metadata,
    )
    return granite_budget_for_task(
        schema_name=spec.target_schema,
        semantic_task=task,
    ).max_attempts


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


def _resolved_document_type_for_plan(
    *,
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    region: SemanticRegionAnnotation,
    target_schema: str,
) -> str:
    if target_schema == "document_observation":
        observation_document_type = _observation_document_type_for_semantic_type(
            region.semantic_type
        )
        if observation_document_type:
            if _document_type_has_source_support(source, observation_document_type):
                return observation_document_type
            return source.family if source.family and source.family != "generic" else "generic"
    document_type = _semantic_document_type(manifest)
    if (
        target_schema == "document_observation"
        and document_type in _OBSERVATION_DOCUMENT_TYPES
        and not _document_type_has_source_support(source, document_type)
    ):
        document_type = None
    if document_type and document_type not in _GENERIC_DOCUMENT_TYPES:
        return document_type
    if source.family and source.family != "generic":
        return source.family
    if target_schema != "document_observation":
        return target_schema
    return document_type or source.family or "generic"


def _document_type_has_source_support(
    source: ExtractionSourceDocument,
    document_type: str,
) -> bool:
    normalized = document_type.strip().lower()
    if source.family.strip().lower() == normalized:
        return True
    return normalized in build_docling_audit(source).suggested_family_hints


def _semantic_document_type(manifest: DocumentSemanticManifest) -> str | None:
    value = manifest.manifest.get("document_type")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _observation_document_type_for_semantic_type(semantic_type: str) -> str | None:
    normalized = semantic_type.strip().lower()
    if normalized == "seller_information_block":
        return "real_estate_title"
    if normalized in {"escrow_summary", "mortgage_payment_summary"}:
        return "mortgage_escrow_statement"
    if normalized in {"dispute_reason_block", "dispute_transaction_table"}:
        return "financial_dispute_form"
    if normalized in {"generic_form_kvp", "unsupported_document_region"}:
        return "generic"
    return None
