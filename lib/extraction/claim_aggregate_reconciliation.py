from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from lib.extraction.claim_resolver import ClaimFamilyProjection, resolve_claims_for_family
from lib.extraction.claims import Claim
from lib.extraction.region_reconciliation import RegionExtraction


@dataclass(frozen=True)
class ClaimRegionProjection:
    claim_projection: ClaimFamilyProjection
    metadata: dict[str, Any]
    claims: tuple[Claim, ...]
    region_count: int


def resolve_claim_regions_for_family(
    *,
    family: str,
    missing_claims_reason: str,
    regions: list[RegionExtraction],
) -> ClaimRegionProjection | None:
    claims: list[Claim] = []
    metadata: dict[str, Any] = {"region_extractions": []}
    region_count = 0

    for region in regions:
        region_claims = tuple(region.claims)
        if not region_claims:
            metadata.setdefault("skipped_region_extractions", []).append(
                {
                    **_region_reference(region),
                    "reason": missing_claims_reason,
                }
            )
            continue
        region_families = source_families_from_claims(region_claims)
        if not _family_is_compatible(requested_family=family, source_families=region_families):
            metadata.setdefault("skipped_region_extractions", []).append(
                {
                    **_region_reference(region),
                    "reason": "aggregate_incompatible_source_family",
                    "source_families": sorted(region_families),
                }
            )
            continue
        claims.extend(_compatible_claims(family=family, claims=region_claims))
        metadata["region_extractions"].append(_region_reference(region))
        region_count += 1

    if not claims:
        return None

    claim_projection = resolve_claims_for_family(family=family, claims=claims)
    if claim_projection.decisions:
        metadata["claim_resolution_decisions"] = [
            decision.__dict__ for decision in claim_projection.decisions
        ]
    metadata["quality_outcome"] = claim_projection.quality_outcome
    source_families = sorted(source_families_from_claims(claims))
    if source_families:
        metadata["source_families"] = source_families

    return ClaimRegionProjection(
        claim_projection=claim_projection,
        metadata=metadata,
        claims=tuple(claims),
        region_count=region_count,
    )


def source_families_from_claims(claims: Iterable[Claim]) -> set[str]:
    families: set[str] = set()
    for claim in claims:
        family, separator, _field_name = claim.canonical_key.partition(".")
        if separator and family:
            families.add(family)
    return families


def _family_is_compatible(*, requested_family: str, source_families: set[str]) -> bool:
    if requested_family == "document_observation":
        return bool(source_families)
    return bool(source_families) and requested_family in source_families


def _compatible_claims(*, family: str, claims: tuple[Claim, ...]) -> tuple[Claim, ...]:
    if family == "document_observation":
        return claims
    return tuple(claim for claim in claims if claim.canonical_key.startswith(f"{family}."))


def _region_reference(region: RegionExtraction) -> dict[str, str]:
    return {
        "extraction_id": str(region.extraction_id),
        "semantic_region_id": str(region.semantic_region_id),
        "semantic_type": region.semantic_type,
    }
