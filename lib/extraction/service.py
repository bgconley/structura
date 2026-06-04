from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID, uuid4

from lib.config import get_settings
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
    observation_candidates_from_extraction,
)
from lib.extraction.region_envelope import (
    region_envelope_from_normalization_json,
    to_normalization_projection,
)
from lib.extraction.region_envelope_candidates import (
    field_candidates_from_region_envelope,
    line_item_candidates_from_region_envelope,
    observation_candidates_from_region_envelope,
)
from lib.extraction.repository import (
    load_extraction_source,
    persist_classification,
    persist_extraction_run,
)
from lib.extraction.rescue_policy import RescuePolicy, RescuePolicyContext
from lib.extraction.schema_registry import ExtractionSchemaRegistry
from lib.extraction.validators import validate_extraction_payload, validate_semantic_region_payload
from lib.jobs import JobService
from lib.jobs.event_payloads import build_extract_document_job_payload
from lib.model_runtime.source_engines import is_model_source_engine
from lib.semantic_annotations.models import SemanticExtractionTask
from lib.semantic_annotations.repository import load_semantic_extraction_task
from lib.semantic_annotations.task_routing import corrected_granite_task_for_semantic_type


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


def _classifier_document_extract_enabled() -> bool:
    # Live Phase 8.5 extraction must be region-scoped from Qwen/Docling semantic
    # targets. The Phase 4 classifier can still persist classification evidence,
    # but it must not launch broad document-level Granite requests.
    return get_settings().model_mode == "fixture"


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
        if decision.family in TARGET_EXTRACTION_SCHEMAS and _classifier_document_extract_enabled():
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
        plan_id: UUID | None = None,
        plan_task_id: UUID | None = None,
        canonical_target_schema: str | None = None,
        compatibility_mode: str | None = None,
        contract_resolution_reason: str | None = None,
        region_envelope_version: str | None = None,
        run_id: str | None = None,
        allow_8b_rescue: bool = False,
        requested_by: str = "system",
        requested_by_user_id: UUID | None = None,
        user_intent_reason: str | None = None,
    ) -> PersistedExtraction:
        if allow_8b_rescue and requested_by == "system":
            raise ExtractionServiceError(
                "Separate semantic rescue has been removed from the active runtime."
            )
        source = self.source_loader(document_id)
        if schema_name not in TARGET_EXTRACTION_SCHEMAS:
            raise ExtractionServiceError(f"Unsupported extraction schema: {schema_name}")
        semantic_task = self._semantic_task_for_document(
            document_id,
            schema_name=schema_name,
            semantic_region_id=semantic_region_id,
            run_metadata={
                "plan_id": str(plan_id) if plan_id else None,
                "plan_task_id": str(plan_task_id) if plan_task_id else None,
                "canonical_target_schema": canonical_target_schema,
                "compatibility_mode": compatibility_mode,
                "contract_resolution_reason": contract_resolution_reason,
                "region_envelope_version": region_envelope_version,
                "run_id": run_id,
            },
        )
        gateway_result = self.gateway.extract(
            source,
            schema_name=schema_name,
            route_profile=route_profile,
            semantic_task=semantic_task,
        )
        model_output_payload = gateway_result.raw_output_json.get("modelOutputPayload")
        if not isinstance(model_output_payload, dict):
            model_output_payload = None
        region_envelope = region_envelope_from_normalization_json(gateway_result.normalization_json)
        if region_envelope is not None:
            gateway_result = replace(
                gateway_result,
                normalized_json=to_normalization_projection(region_envelope),
            )
        validation = (
            validate_semantic_region_payload(
                gateway_result.normalized_json,
                model_output_schema_name=gateway_result.model_output_schema_name,
                model_output_payload=model_output_payload,
            )
            if semantic_task is not None
            and is_model_source_engine(gateway_result.route.source_engine)
            else validate_extraction_payload(
                schema_name,
                gateway_result.normalized_json,
                registry=self.registry,
            )
        )
        gateway_result.normalized_json["validation"] = validation.as_json()
        normalized_schema_name = str(
            gateway_result.normalized_json.get("schema_name") or schema_name
        )
        require_concrete_candidate_evidence = (
            semantic_task is not None and gateway_result.route.source_engine != "system"
        )
        if region_envelope is not None:
            field_candidates = field_candidates_from_region_envelope(
                document_id=document_id,
                envelope=region_envelope,
                validation=validation,
                source_engine=gateway_result.route.source_engine,
                require_concrete_evidence=require_concrete_candidate_evidence,
            )
            line_item_candidates = line_item_candidates_from_region_envelope(
                envelope=region_envelope,
                validation=validation,
                source_engine=gateway_result.route.source_engine,
                require_concrete_evidence=require_concrete_candidate_evidence,
            )
            observation_candidates = observation_candidates_from_region_envelope(
                envelope=region_envelope,
                validation=validation,
                require_concrete_evidence=require_concrete_candidate_evidence,
            )
        else:
            field_candidates = field_candidates_from_extraction(
                document_id=document_id,
                schema_name=normalized_schema_name,
                payload=gateway_result.normalized_json,
                validation=validation,
                source_engine=gateway_result.route.source_engine,
                require_concrete_evidence=require_concrete_candidate_evidence,
            )
            line_item_candidates = line_item_candidates_from_extraction(
                schema_name=normalized_schema_name,
                payload=gateway_result.normalized_json,
                validation=validation,
                source_engine=gateway_result.route.source_engine,
                require_concrete_evidence=require_concrete_candidate_evidence,
            )
            observation_candidates = observation_candidates_from_extraction(
                schema_name=normalized_schema_name,
                payload=gateway_result.normalized_json,
                validation=validation,
                require_concrete_evidence=require_concrete_candidate_evidence,
            )
        persisted = self.persister(
            gateway_result,
            source=source,
            validation=validation,
            field_candidates=field_candidates,
            line_item_candidates=line_item_candidates,
            observation_candidates=observation_candidates,
            semantic_task=semantic_task,
        )
        self.rescue_policy.decide(
            RescuePolicyContext(
                allow_8b_rescue=allow_8b_rescue,
                validation=validation,
                semantic_task=semantic_task,
                candidate_count=(
                    len(field_candidates) + len(line_item_candidates) + len(observation_candidates)
                ),
                prior_rescue_attempted=False,
            )
        )
        return persisted

    def _semantic_task_for_document(
        self,
        document_id: UUID,
        *,
        schema_name: str,
        semantic_region_id: UUID | None,
        run_metadata: dict[str, str | None],
    ) -> SemanticExtractionTask | None:
        if semantic_region_id is None:
            return None
        task = self.semantic_task_loader(semantic_region_id)
        if task.document_id != document_id:
            raise ExtractionServiceError("Semantic extraction task document mismatch.")
        repaired_task = task
        metadata = dict(task.metadata)
        if task.target_schema and task.target_schema != schema_name:
            metadata["original_target_schema"] = task.target_schema
            metadata["target_schema_repaired"] = True
            repaired_task = replace(repaired_task, target_schema=schema_name)
        granite_task, repair = corrected_granite_task_for_semantic_type(
            semantic_type=task.semantic_type,
            granite_task=task.granite_task,
        )
        if repair is not None:
            metadata["semantic_task_repair"] = repair
            repaired_task = replace(repaired_task, granite_task=granite_task or task.granite_task)
        if metadata != task.metadata:
            repaired_task = replace(repaired_task, metadata=metadata)
        lineage_metadata = {
            key: value for key, value in run_metadata.items() if value not in (None, "")
        }
        if lineage_metadata:
            repaired_task = replace(
                repaired_task,
                metadata={**repaired_task.metadata, **lineage_metadata},
            )
        return repaired_task
