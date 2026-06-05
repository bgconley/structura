from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from lib.extraction.claim_aggregate_reconciliation import (
    resolve_claim_regions_for_family,
)
from lib.extraction.region_reconciliation import RegionExtraction


def reconcile_document_observation_region_extractions(
    *,
    document_id: UUID,
    created_at: datetime,
    regions: list[RegionExtraction],
) -> dict[str, Any] | None:
    claim_regions = resolve_claim_regions_for_family(
        family="document_observation",
        missing_claims_reason="claims_required_for_document_observation_aggregate",
        regions=regions,
    )
    if claim_regions is None:
        return None

    claim_projection = claim_regions.claim_projection
    if not claim_projection.observations:
        return None

    metadata = claim_regions.metadata

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
