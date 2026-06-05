from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from lib.extraction.claims import Claim
from lib.extraction.region_envelope import RegionExtractionEnvelope


@dataclass(frozen=True)
class RegionExtraction:
    extraction_id: UUID
    semantic_region_id: UUID
    semantic_type: str
    normalized_json: dict[str, Any]
    region_envelope: RegionExtractionEnvelope | None = None
    claims: Sequence[Claim] = ()
