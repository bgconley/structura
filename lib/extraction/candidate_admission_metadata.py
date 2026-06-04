from __future__ import annotations

from dataclasses import replace

from lib.extraction.models import (
    CandidateFact,
    LineItemCandidateFact,
    ObservationCandidateFact,
)

__all__ = [
    "with_candidate_admission_fingerprint",
    "with_line_item_admission_fingerprint",
    "with_observation_admission_fingerprint",
]


def with_candidate_admission_fingerprint(
    candidate: CandidateFact,
    fingerprint: str,
) -> CandidateFact:
    return replace(
        candidate,
        validation={**candidate.validation, "candidateAdmissionFingerprint": fingerprint},
    )


def with_line_item_admission_fingerprint(
    candidate: LineItemCandidateFact,
    fingerprint: str,
) -> LineItemCandidateFact:
    return replace(
        candidate,
        validation={**candidate.validation, "candidateAdmissionFingerprint": fingerprint},
    )


def with_observation_admission_fingerprint(
    candidate: ObservationCandidateFact,
    fingerprint: str,
) -> ObservationCandidateFact:
    return replace(
        candidate,
        metadata={**candidate.metadata, "candidateAdmissionFingerprint": fingerprint},
    )
