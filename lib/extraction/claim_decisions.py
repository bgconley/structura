from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimResolutionDecision:
    canonical_key: str
    decision: str
    reason_code: str
    selected_claim_id: str | None
    rejected_claim_ids: tuple[str, ...] = ()
