from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.claims import Claim
from lib.extraction.reconciliation import RegionExtraction


def reconcile_document_observation_region_extractions(
    *,
    document_id: UUID,
    created_at: datetime,
    regions: list[RegionExtraction],
) -> dict[str, Any] | None:
    claims: list[Claim] = []
    metadata: dict[str, Any] = {"region_extractions": []}
    for region in regions:
        if not region.claims:
            continue
        claims.extend(region.claims)
        metadata["region_extractions"].append(_region_reference(region))

    if not claims:
        return None

    claim_projection = resolve_claims_for_family(
        family="document_observation",
        claims=claims,
    )
    if not claim_projection.observations:
        return None

    metadata["claim_resolution_decisions"] = [
        decision.__dict__ for decision in claim_projection.decisions
    ]
    source_families = sorted(
        {
            str(observation["family"])
            for observation in claim_projection.observations
            if observation.get("family") not in (None, "")
        }
    )
    if source_families:
        metadata["source_families"] = source_families

    return {
        "schema_name": "document_observation",
        "schema_version": "v1",
        "document_id": str(document_id),
        "observations": claim_projection.observations,
        "confidence": {},
        "created_at": created_at.isoformat(),
        "validation": {"needs_review": True, "checks": []},
        "metadata": metadata,
    }


def _region_reference(region: RegionExtraction) -> dict[str, str]:
    return {
        "extraction_id": str(region.extraction_id),
        "semantic_region_id": str(region.semantic_region_id),
        "semantic_type": region.semantic_type,
    }
