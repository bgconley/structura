"""Versioned immutable DTOs for structure-derived claims, never accepted facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, model_validator

from lib.document_parsing.structure import Sha256, SourceBox
from lib.document_processing.models import ProcessingBinding, content_digest
from lib.extraction.claim_registry import CLAIM_FAMILY_REGISTRIES
from lib.extraction.native_claims.values import NativeMoney, NativeValueType, type_recorded_text


class NativeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class NativeClaimConfiguration(NativeModel):
    schema_version: Literal["native_claim_configuration.v1"] = "native_claim_configuration.v1"
    normalizer_version: Literal["recorded-text-exact-v1"] = "recorded-text-exact-v1"
    key_mapping_version: Literal["explicit-anchored-key-v1"] = "explicit-anchored-key-v1"
    review_policy_version: Literal["model-derived-human-review-v1"] = (
        "model-derived-human-review-v1"
    )
    derivation: Literal["structure_normalization"] = "structure_normalization"
    registry_sha256: Sha256 = Field(
        default_factory=lambda: content_digest(
            {key: asdict(value) for key, value in sorted(CLAIM_FAMILY_REGISTRIES.items())}
        )
    )

    @property
    def fingerprint(self) -> str:
        return content_digest(self.model_dump(mode="json"))


class NativeAnchorRequest(NativeModel):
    element_id: UUID
    table_id: UUID | None = None
    cell_id: UUID | None = None
    text_start: int = Field(ge=0)
    text_end: int = Field(gt=0)

    @model_validator(mode="after")
    def complete_locator(self) -> NativeAnchorRequest:
        if (self.table_id is None) != (self.cell_id is None) or self.text_end <= self.text_start:
            raise ValueError("Native claim locator is incomplete.")
        return self


class NativeClaimRequest(NativeModel):
    canonical_key: str = Field(min_length=1, max_length=200, pattern=r"^[a-z][a-z0-9_.]*$")
    value_type: NativeValueType
    anchor: NativeAnchorRequest


class NativePageRequest(NativeModel):
    schema_version: Literal["native_claim_page_request.v1"] = "native_claim_page_request.v1"
    derivation: Literal["structure_normalization"] = "structure_normalization"
    page_number: int = Field(gt=0, le=500)
    disposition: Literal["complete", "partial", "no_extraction_target", "insufficient_signal"]
    reasons: tuple[
        Literal["ambiguous_structure", "unsupported_value", "source_incomplete", "no_target"], ...
    ] = ()
    claims: tuple[NativeClaimRequest, ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def truthful_coverage(self) -> NativePageRequest:
        if self.disposition == "complete" and (not self.claims or self.reasons):
            raise ValueError("Complete claim inventory requires claims without omissions.")
        if self.disposition in {"no_extraction_target", "insufficient_signal"} and self.claims:
            raise ValueError("Abstention pages cannot contain claims.")
        if self.disposition != "complete" and not self.reasons:
            raise ValueError("Incomplete or empty inventory requires an explicit reason.")
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("Claim coverage reasons must be unique.")
        return self


class NativeClaimAnchor(NativeModel):
    schema_version: Literal["native_claim_anchor.v2"] = "native_claim_anchor.v2"
    parse_generation_id: UUID
    page_number: int = Field(gt=0)
    page_id: UUID
    source_page_image_sha256: Sha256
    element_id: UUID
    table_id: UUID | None = None
    cell_id: UUID | None = None
    row_index: int | None = Field(default=None, ge=0)
    text_start: int = Field(ge=0)
    text_end: int = Field(gt=0)
    source_text: str
    bbox: SourceBox
    coordinate_space: Literal["rendered_source_pixels"] = "rendered_source_pixels"
    text_origin: Literal["model_transcription"] = "model_transcription"


class NativeClaim(NativeModel):
    schema_version: Literal["native_claim.v2"] = "native_claim.v2"
    claim_id: Sha256
    claim_set_id: UUID
    document_id: UUID
    canonical_key: str
    value_type: NativeValueType
    typed_value: StrictStr | StrictBool | NativeMoney
    raw_value: str
    anchor: NativeClaimAnchor
    physical_source_id: Sha256
    group_id: Sha256 | None
    source_engine: Literal["qwen3_8_27b"] = "qwen3_8_27b"
    derivation: Literal["structure_normalization"] = "structure_normalization"
    interpretation_origin: Literal["deterministic_normalization"] = "deterministic_normalization"
    configuration_sha256: Sha256
    checkpoint_sha256: Sha256
    invocation_request_id: UUID
    raw_output_sha256: Sha256
    requires_review: Literal[True] = True
    source_pixel_support: Literal["not_evaluated"] = "not_evaluated"

    @model_validator(mode="after")
    def value_is_derived(self) -> NativeClaim:
        if self.raw_value != self.anchor.source_text or self.typed_value != type_recorded_text(
            self.value_type, self.raw_value
        ):
            raise ValueError("Native typed value is not the recorded normalization result.")
        expected = content_digest(
            {
                "claim_set_id": str(self.claim_set_id),
                "physical_source_id": self.physical_source_id,
                "canonical_key": self.canonical_key,
            }
        )
        if expected != self.claim_id:
            raise ValueError("Native logical claim identity is invalid.")
        physical = content_digest(
            {
                "parse_generation_id": str(self.anchor.parse_generation_id),
                "page_id": str(self.anchor.page_id),
                "element_id": str(self.anchor.element_id),
                "table_id": str(self.anchor.table_id) if self.anchor.table_id else None,
                "row_index": self.anchor.row_index,
            }
        )
        group = physical if ".line_item." in self.canonical_key else None
        if self.physical_source_id != physical or self.group_id != group:
            raise ValueError("Native physical source identity is invalid.")
        return self

    @property
    def fingerprint(self) -> str:
        return content_digest(self.model_dump(mode="json"))


@dataclass(frozen=True)
class NativeClaimBinding:
    processing: ProcessingBinding
    claim_set_id: UUID
