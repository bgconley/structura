from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lib.extraction.classification import TARGET_EXTRACTION_SCHEMAS, classify_document
from lib.extraction.gateway import DoclingHeuristicGateway, ExtractionGateway
from lib.extraction.models import ClassificationDecision, PersistedExtraction
from lib.extraction.normalization import (
    field_candidates_from_extraction,
    line_item_candidates_from_extraction,
)
from lib.extraction.repository import (
    load_extraction_source,
    persist_classification,
    persist_extraction_run,
)
from lib.extraction.schema_registry import ExtractionSchemaRegistry
from lib.extraction.validators import validate_extraction_payload
from lib.jobs import JobService


class ExtractionServiceError(Exception):
    pass


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
        jobs: JobService | None = None,
    ) -> None:
        self.registry = registry or ExtractionSchemaRegistry()
        self.gateway = gateway or DoclingHeuristicGateway()
        self.jobs = jobs or JobService()

    def classify_document(
        self,
        document_id: UUID,
        *,
        force_reclassify: bool = False,
    ) -> ClassificationResult:
        del force_reclassify
        source = load_extraction_source(document_id)
        decision = classify_document(source, registry=self.registry)
        extraction_id = persist_classification(decision, source=source)
        queued_job_id = None
        if decision.family in TARGET_EXTRACTION_SCHEMAS:
            job = self.jobs.create_job(
                job_type="extract",
                household_id=source.household_id,
                document_id=document_id,
                payload={
                    "schema_name": "extract_document_job",
                    "schema_version": "v1",
                    "document_id": str(document_id),
                    "target_schema_name": decision.family,
                    "target_schema_version": "v1",
                    "route_profile": decision.route_profile,
                    "requested_by": "system",
                },
                priority=35,
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
    ) -> PersistedExtraction:
        source = load_extraction_source(document_id)
        if schema_name not in TARGET_EXTRACTION_SCHEMAS:
            raise ExtractionServiceError(f"Unsupported extraction schema: {schema_name}")
        gateway_result = self.gateway.extract(
            source,
            schema_name=schema_name,
            route_profile=route_profile,
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
        return persist_extraction_run(
            gateway_result,
            source=source,
            validation=validation,
            field_candidates=field_candidates,
            line_item_candidates=line_item_candidates,
        )
