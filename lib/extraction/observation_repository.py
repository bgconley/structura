from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.extraction.candidate_value_parsing import confidence_or_none
from lib.extraction.errors import ExtractionRepositoryError
from lib.extraction.models import ObservationCandidateFact


def insert_observation_candidate(
    cur: Any,
    document_id: UUID,
    extraction_id: UUID,
    source_engine: str,
    candidate: ObservationCandidateFact,
    *,
    semantic_annotation_id: UUID | None,
    source_semantic_region_id: UUID | None,
    semantic_type: str | None,
    model_output_schema_name: str | None,
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO extraction_observations
          (
            document_id, extraction_id, semantic_annotation_id,
            source_semantic_region_id, semantic_type, source_engine,
            model_output_schema_name, observation_family, field_name,
            value_type, value_json, confidence, evidence_json, validation_json,
            status, metadata_json
          )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
          %s, %s::jsonb, %s::jsonb, %s, %s::jsonb
        )
        RETURNING *
        """,
        (
            document_id,
            extraction_id,
            semantic_annotation_id,
            source_semantic_region_id,
            semantic_type,
            source_engine,
            model_output_schema_name,
            candidate.observation_family,
            candidate.field_name,
            candidate.value_type,
            Jsonb(candidate.value),
            confidence_or_none(candidate.confidence),
            Jsonb(candidate.evidence),
            Jsonb(candidate.validation),
            candidate.status,
            Jsonb(candidate.metadata),
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ExtractionRepositoryError("Observation candidate insert failed.")
    return dict(row)
