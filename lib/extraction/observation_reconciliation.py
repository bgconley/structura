from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from lib.extraction.claim_aggregate_reconciliation import (
    resolve_claim_regions_for_family,
)
from lib.extraction.claim_projection import project_document_observation_payload
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

    return project_document_observation_payload(
        document_id=document_id,
        created_at=created_at,
        projection=claim_regions.claim_projection,
        metadata=claim_regions.metadata,
    )
