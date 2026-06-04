from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.extraction.models import (
    CandidateFact,
    LineItemCandidateFact,
    ObservationCandidateFact,
    ValidationReport,
)
from lib.extraction.normalization import (
    field_candidates_from_extraction,
    line_item_candidates_from_extraction,
    observation_candidates_from_extraction,
)
from lib.extraction.region_envelope import RegionExtractionEnvelope, to_normalization_projection


def field_candidates_from_region_envelope(
    *,
    document_id: UUID,
    envelope: RegionExtractionEnvelope,
    validation: ValidationReport,
    source_engine: str,
    require_concrete_evidence: bool = False,
) -> list[CandidateFact]:
    projection = to_normalization_projection(envelope)
    return field_candidates_from_extraction(
        document_id=document_id,
        schema_name=_schema_name(projection, envelope),
        payload=projection,
        validation=validation,
        source_engine=source_engine,
        require_concrete_evidence=require_concrete_evidence,
    )


def line_item_candidates_from_region_envelope(
    *,
    envelope: RegionExtractionEnvelope,
    validation: ValidationReport,
    source_engine: str,
    require_concrete_evidence: bool = False,
) -> list[LineItemCandidateFact]:
    projection = to_normalization_projection(envelope)
    return line_item_candidates_from_extraction(
        schema_name=_schema_name(projection, envelope),
        payload=projection,
        validation=validation,
        source_engine=source_engine,
        require_concrete_evidence=require_concrete_evidence,
    )


def observation_candidates_from_region_envelope(
    *,
    envelope: RegionExtractionEnvelope,
    validation: ValidationReport,
    require_concrete_evidence: bool = False,
) -> list[ObservationCandidateFact]:
    projection = to_normalization_projection(envelope)
    return observation_candidates_from_extraction(
        schema_name=_schema_name(projection, envelope),
        payload=projection,
        validation=validation,
        require_concrete_evidence=require_concrete_evidence,
    )


def _schema_name(projection: dict[str, Any], envelope: RegionExtractionEnvelope) -> str:
    return str(
        projection.get("schema_name") or envelope.target_schema or envelope.resolved_document_type
    )
