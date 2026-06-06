from __future__ import annotations

from uuid import UUID

from lib.extraction.claim_candidates import (
    field_candidates_from_claims,
    line_item_candidates_from_claims,
    observation_candidates_from_claims,
)
from lib.extraction.claim_registry import CLAIM_FAMILY_REGISTRIES
from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.models import (
    CandidateFact,
    LineItemCandidateFact,
    ObservationCandidateFact,
    ValidationReport,
)
from lib.extraction.region_envelope import RegionExtractionEnvelope


def field_candidates_from_region_envelope(
    *,
    document_id: UUID,
    envelope: RegionExtractionEnvelope,
    validation: ValidationReport,
    source_engine: str,
    require_concrete_evidence: bool = False,
) -> list[CandidateFact]:
    return field_candidates_from_claims(
        document_id=document_id,
        family=_claim_family(envelope),
        claims=claims_from_region_envelope(envelope),
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
    return line_item_candidates_from_claims(
        family=_claim_family(envelope),
        claims=claims_from_region_envelope(envelope),
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
    return observation_candidates_from_claims(
        family=_claim_family(envelope),
        claims=claims_from_region_envelope(envelope),
        validation=validation,
        require_concrete_evidence=require_concrete_evidence,
    )


def _claim_family(envelope: RegionExtractionEnvelope) -> str:
    resolved = envelope.resolved_document_type.strip()
    if resolved in CLAIM_FAMILY_REGISTRIES:
        return resolved
    target = (envelope.target_schema or "").strip()
    return target or resolved or "document_observation"
