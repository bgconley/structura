from __future__ import annotations

from typing import Any

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.region_envelope import RegionExtractionEnvelope


def claim_evidence_validation_payload(envelope: RegionExtractionEnvelope) -> dict[str, Any]:
    """Build a validation-only evidence payload from admissible typed Claims."""
    return {
        "claims": [
            {
                "canonical_key": claim.canonical_key,
                "evidence": list(claim.evidence),
            }
            for claim in claims_from_region_envelope(envelope)
        ]
    }
