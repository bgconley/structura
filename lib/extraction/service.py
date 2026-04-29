from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from lib.db.connection import db_connection
from lib.extraction.classification import TARGET_EXTRACTION_SCHEMAS, classify_document
from lib.extraction.gateway import ExtractionGateway
from lib.extraction.gateways.routing import default_extraction_gateway
from lib.extraction.models import (
    ClassificationDecision,
    ExtractionSourceDocument,
    PersistedExtraction,
)
from lib.extraction.normalization import (
    field_candidates_from_extraction,
    line_item_candidates_from_extraction,
)
from lib.extraction.repository import (
    load_extraction_source,
    persist_classification,
    persist_extraction_run,
)
from lib.extraction.rescue_policy import RescuePolicy, RescuePolicyContext
from lib.extraction.schema_registry import ExtractionSchemaRegistry
from lib.extraction.validators import validate_extraction_payload
from lib.jobs import JobService
from lib.jobs.event_payloads import (
    build_extract_document_job_payload,
    build_semantic_annotate_document_job_payload,
)
from lib.semantic_annotations.jobs import enqueue_semantic_annotation_job
from lib.semantic_annotations.models import SemanticExtractionTask
from lib.semantic_annotations.repository import load_semantic_extraction_task


class ExtractionServiceError(Exception):
    pass


class CreatedJob(Protocol):
    job_id: UUID


class JobCreator(Protocol):
    def create_job(self, **kwargs: object) -> CreatedJob: ...


@dataclass(frozen=True)
class ClassificationResult:
    decision: ClassificationDecision
    extraction_id: UUID
    queued_extraction_job_id: UUID | None


class ExtractionService:
    def __init__(
        self,
        *,
        registry: ExtractionSchemaRegistry | None = None,
        gateway: ExtractionGateway | None = None,
        jobs: JobCreator | None = None,
        source_loader: Callable[[UUID], ExtractionSourceDocument] = load_extraction_source,
        semantic_task_loader: Callable[[UUID], SemanticExtractionTask] = (
            load_semantic_extraction_task
        ),
        persister: Callable[..., PersistedExtraction] = persist_extraction_run,
        rescue_policy: RescuePolicy | None = None,
    ) -> None:
        self.registry = registry or ExtractionSchemaRegistry()
        self.gateway = gateway or default_extraction_gateway()
        self.jobs = jobs or JobService()
        self.source_loader = source_loader
        self.semantic_task_loader = semantic_task_loader
        self.persister = persister
        self.rescue_policy = rescue_policy or RescuePolicy()

    def classify_document(
        self,
        document_id: UUID,
        *,
        force_reclassify: bool = False,
    ) -> ClassificationResult:
        del force_reclassify
        source = self.source_loader(document_id)
        decision = classify_document(source, registry=self.registry)
        extraction_id = persist_classification(decision, source=source)
        queued_job_id = None
        if decision.family in TARGET_EXTRACTION_SCHEMAS:
            priority = 35
            job_id = uuid4()
            job = self.jobs.create_job(
                job_id=job_id,
                job_type="extract",
                household_id=source.household_id,
                document_id=document_id,
                payload=build_extract_document_job_payload(
                    job_id=job_id,
                    document_id=document_id,
                    target_schema_name=decision.family,
                    target_schema_version="v1",
                    route_profile=decision.route_profile,
                    requested_by="system",
                    priority=priority,
                ),
                priority=priority,
                queue_name="extraction",
            )
            queued_job_id = job.job_id
        return ClassificationResult(
            decision=decision,
            extraction_id=extraction_id,
            queued_extraction_job_id=queued_job_id,
        )

    def extract_document(
        self,
        document_id: UUID,
        *,
        schema_name: str,
        route_profile: str = "docling_plus_structured_extraction",
        semantic_region_id: UUID | None = None,
        allow_8b_rescue: bool = False,
        requested_by: str = "system",
        requested_by_user_id: UUID | None = None,
        user_intent_reason: str | None = None,
    ) -> PersistedExtraction:
        if allow_8b_rescue and requested_by == "system":
            raise ExtractionServiceError(
                "Qwen3-VL 8B rescue requires explicit user or agent intent."
            )
        source = self.source_loader(document_id)
        if schema_name not in TARGET_EXTRACTION_SCHEMAS:
            raise ExtractionServiceError(f"Unsupported extraction schema: {schema_name}")
        semantic_task = self._semantic_task_for_document(
            document_id,
            schema_name=schema_name,
            semantic_region_id=semantic_region_id,
        )
        gateway_result = self.gateway.extract(
            source,
            schema_name=schema_name,
            route_profile=route_profile,
            semantic_task=semantic_task,
        )
        validation = validate_extraction_payload(
            schema_name,
            gateway_result.normalized_json,
            registry=self.registry,
        )
        gateway_result.normalized_json["validation"] = validation.as_json()
        field_candidates = field_candidates_from_extraction(
            document_id=document_id,
            schema_name=schema_name,
            payload=gateway_result.normalized_json,
            validation=validation,
            source_engine=gateway_result.route.source_engine,
        )
        line_item_candidates = line_item_candidates_from_extraction(
            schema_name=schema_name,
            payload=gateway_result.normalized_json,
            validation=validation,
            source_engine=gateway_result.route.source_engine,
        )
        persisted = self.persister(
            gateway_result,
            source=source,
            validation=validation,
            field_candidates=field_candidates,
            line_item_candidates=line_item_candidates,
        )
        rescue_decision = self.rescue_policy.decide(
            RescuePolicyContext(
                allow_8b_rescue=allow_8b_rescue,
                validation=validation,
                semantic_task=semantic_task,
                candidate_count=len(field_candidates) + len(line_item_candidates),
                prior_rescue_attempted=False,
            )
        )
        if rescue_decision.outcome == "rescue_permitted_once" and semantic_task is not None:
            self._enqueue_rescue_semantic_pass(
                source,
                semantic_task,
                failure_class=rescue_decision.failure_class,
                allow_8b_rescue=allow_8b_rescue,
                requested_by=requested_by,
                requested_by_user_id=requested_by_user_id,
                user_intent_reason=user_intent_reason,
            )
        return persisted

    def _semantic_task_for_document(
        self,
        document_id: UUID,
        *,
        schema_name: str,
        semantic_region_id: UUID | None,
    ) -> SemanticExtractionTask | None:
        if semantic_region_id is None:
            return None
        task = self.semantic_task_loader(semantic_region_id)
        if task.document_id != document_id:
            raise ExtractionServiceError("Semantic extraction task document mismatch.")
        if task.target_schema and task.target_schema != schema_name:
            raise ExtractionServiceError("Semantic extraction task schema mismatch.")
        return task

    def _enqueue_rescue_semantic_pass(
        self,
        source: ExtractionSourceDocument,
        semantic_task: SemanticExtractionTask,
        *,
        failure_class: str,
        allow_8b_rescue: bool,
        requested_by: str,
        requested_by_user_id: UUID | None,
        user_intent_reason: str | None,
    ) -> None:
        if isinstance(self.jobs, JobService):
            with db_connection() as conn:
                with conn.cursor() as cur:
                    enqueue_semantic_annotation_job(
                        cur,
                        document_id=source.document_id,
                        household_id=source.household_id,
                        quality_mode="rescue",
                        semantic_quality_mode="smart",
                        allow_8b_rescue=allow_8b_rescue,
                        requested_by=requested_by,
                        requested_by_user_id=requested_by_user_id,
                        user_intent_reason=user_intent_reason,
                        reason="phase8_5.validation_failed_rescue",
                        source_semantic_region_id=semantic_task.region_id,
                        rescue_failure_class=failure_class,
                        dedupe_existing=True,
                        priority=26,
                    )
                conn.commit()
            return
        job_id = uuid4()
        self.jobs.create_job(
            job_id=job_id,
            job_type="semantic_annotate",
            household_id=source.household_id,
            document_id=source.document_id,
            payload=build_semantic_annotate_document_job_payload(
                job_id=job_id,
                document_id=source.document_id,
                quality_mode="rescue",
                semantic_quality_mode="smart",
                allow_8b_rescue=allow_8b_rescue,
                requested_by=requested_by,
                requested_by_user_id=requested_by_user_id,
                user_intent_reason=user_intent_reason,
                reason="phase8_5.validation_failed_rescue",
                source_semantic_region_id=semantic_task.region_id,
                metadata={"failure_class": failure_class},
            ),
            priority=26,
            queue_name="semantic-annotations",
        )
