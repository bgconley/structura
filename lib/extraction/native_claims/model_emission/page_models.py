"""Retained page accounting, including explicit zero-claim classification outcomes."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from lib.document_parsing.page_understanding.classification import PageClassification
from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.document_parsing.structure import Sha256
from lib.extraction.native_claims.model_emission.models import (
    ModelClaimAnchor,
    NativeMemberBinding,
    NativeModelClaim,
)
from lib.extraction.native_claims.models import NativeModel


class BoundPageEvidence(NativeModel):
    pointer: str = Field(min_length=1, max_length=1000)
    anchor: ModelClaimAnchor


class NativeModelPageRecord(NativeModel):
    schema_version: Literal["native_model_claim_page.v1"] = "native_model_claim_page.v1"
    derivation: Literal["model_emission"] = "model_emission"
    page_number: int = Field(ge=1, le=500, strict=True)
    page_id: UUID
    checkpoint_sha256: Sha256
    raw_output_sha256: Sha256
    classification_json: dict[str, Any]
    classification_sha256: Sha256
    coverage_json: dict[str, Any]
    coverage_sha256: Sha256
    bound_evidence: tuple[BoundPageEvidence, ...]
    members: tuple[NativeMemberBinding, ...] = Field(max_length=3000)
    requires_review: Literal[True] = True
    source_pixel_support: Literal["not_evaluated"] = "not_evaluated"

    @model_validator(mode="after")
    def exact_accounting(self) -> "NativeModelPageRecord":
        PageClassification.model_validate(self.classification_json)
        if (
            canonical_digest(self.classification_json) != self.classification_sha256
            or canonical_digest(self.coverage_json) != self.coverage_sha256
            or "claims" in self.coverage_json
        ):
            raise ValueError("Native page accounting differs from its retained members.")
        if tuple(m.index for m in self.members) != tuple(range(len(self.members))):
            raise ValueError("Native page member inventory is incomplete or reordered.")
        if len({m.claim_id for m in self.members}) != len(self.members):
            raise ValueError("Native page contains duplicate physical claim identities.")
        if len({e.pointer for e in self.bound_evidence}) != len(self.bound_evidence):
            raise ValueError("Native page evidence pointers must be distinct.")
        return self


def page_digest(record: NativeModelPageRecord, claims: tuple[NativeModelClaim, ...]) -> str:
    return canonical_digest(
        {
            "page": record.model_dump(mode="json"),
            "claims": [c.model_dump(mode="json") for c in sorted(claims, key=lambda c: c.claim_id)],
        }
    )
