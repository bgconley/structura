from __future__ import annotations

from dataclasses import dataclass, replace

from lib.extraction.candidate_admission import (
    CandidateAdmissionContext,
    CandidateAdmissionResult,
    admit_extraction_candidates,
    normalization_json_with_candidate_admission,
    rejected_candidates_from_payload,
)
from lib.extraction.models import (
    CandidateFact,
    ExtractionRunScope,
    ExtractionSourceDocument,
    GatewayExtraction,
    LineItemCandidateFact,
    ObservationCandidateFact,
)
from lib.extraction.region_envelope import region_envelope_from_normalization_json
from lib.model_runtime.source_engines import is_model_source_engine


@dataclass(frozen=True)
class CandidateAdmissionBoundaryResult:
    extraction: GatewayExtraction
    admission: CandidateAdmissionResult


def apply_candidate_admission_boundary(
    *,
    extraction: GatewayExtraction,
    source: ExtractionSourceDocument,
    run_scope: ExtractionRunScope,
    field_candidates: list[CandidateFact],
    line_item_candidates: list[LineItemCandidateFact],
    observation_candidates: list[ObservationCandidateFact],
) -> CandidateAdmissionBoundaryResult:
    context = CandidateAdmissionContext(
        document_id=source.document_id,
        run_scope=run_scope,
        source_engine=extraction.route.source_engine,
        model_output_schema_name=extraction.model_output_schema_name,
        run_id=_optional_str(run_scope.metadata.get("run_id")),
    )
    require_concrete_evidence = (
        run_scope.extraction_scope == "semantic_region"
        and extraction.route.source_engine != "system"
    )
    normalized_schema_name = str(
        extraction.normalized_json.get("schema_name") or extraction.schema_name
    )
    admission = admit_extraction_candidates(
        context=context,
        field_candidates=field_candidates,
        line_item_candidates=line_item_candidates,
        observation_candidates=observation_candidates,
        rejected_candidate_payloads=_rejected_payloads_for_boundary(
            extraction=extraction,
            run_scope=run_scope,
            normalized_schema_name=normalized_schema_name,
            context=context,
            require_concrete_evidence=require_concrete_evidence,
        ),
    )
    return CandidateAdmissionBoundaryResult(
        extraction=replace(
            extraction,
            normalization_json=normalization_json_with_candidate_admission(
                extraction.normalization_json,
                admission,
            ),
        ),
        admission=admission,
    )


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _rejected_payloads_for_boundary(
    *,
    extraction: GatewayExtraction,
    run_scope: ExtractionRunScope,
    normalized_schema_name: str,
    context: CandidateAdmissionContext,
    require_concrete_evidence: bool,
) -> list[dict[str, object]]:
    if run_scope.extraction_scope == "semantic_region" and is_model_source_engine(
        context.source_engine
    ):
        return []
    if (
        run_scope.extraction_scope == "semantic_region"
        and region_envelope_from_normalization_json(extraction.normalization_json) is not None
    ):
        return []
    return rejected_candidates_from_payload(
        schema_name=normalized_schema_name,
        payload=extraction.normalized_json,
        context=context,
        require_concrete_evidence=require_concrete_evidence,
    )
