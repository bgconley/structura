"""Versioned retained model proposals; 105 exact-normalization DTOs remain unchanged."""

from typing import Any, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from lib.document_parsing.page_understanding.claims import ProposedClaim
from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.document_parsing.structure import Sha256, SourceBox
from lib.document_processing.configuration_types import UnderstandingDefinitions
from lib.extraction.native_claims.model_emission.identity import claim_identity, physical_identity
from lib.extraction.native_claims.models import NativeModel


class NativeModelEmissionConfiguration(NativeModel):
    schema_version: Literal["native_model_emission_configuration.v1"] = (
        "native_model_emission_configuration.v1"
    )
    derivation: Literal["model_emission"] = "model_emission"
    importer_version: Literal["raw-member-import-v1"] = "raw-member-import-v1"
    review_policy_version: Literal["model-derived-human-review-v1"] = (
        "model-derived-human-review-v1"
    )
    definitions: UnderstandingDefinitions
    implementation_sha256: Sha256

    @property
    def fingerprint(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class ModelClaimAnchor(NativeModel):
    parse_generation_id: UUID
    page_number: int = Field(ge=1, le=500, strict=True)
    page_id: UUID
    source_page_image_sha256: Sha256
    element_id: UUID
    table_id: UUID | None
    cell_id: UUID | None
    cell_row: int | None = Field(ge=0, strict=True)
    cell_column: int | None = Field(ge=0, strict=True)
    text_start: int = Field(ge=0, strict=True)
    text_end: int = Field(gt=0, strict=True)
    source_text: str = Field(min_length=1, max_length=4096)
    bbox: SourceBox
    coordinate_space: Literal["rendered_source_pixels"] = "rendered_source_pixels"
    text_origin: Literal["model_transcription"] = "model_transcription"

    @model_validator(mode="after")
    def complete_occurrence(self) -> "ModelClaimAnchor":
        refs = (self.table_id, self.cell_id, self.cell_row, self.cell_column)
        if any(v is None for v in refs) != all(v is None for v in refs):
            raise ValueError("Model claim cell binding is incomplete.")
        if (
            self.text_end <= self.text_start
            or len(self.source_text) != self.text_end - self.text_start
        ):
            raise ValueError("Model claim occurrence span is inconsistent.")
        return self


class ModelClaimRow(NativeModel):
    kind: Literal["table_row", "structural_row"]
    element_id: UUID
    table_id: UUID | None
    row_index: int | None = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def complete_row(self) -> "ModelClaimRow":
        if (self.kind == "table_row") != (self.table_id is not None and self.row_index is not None):
            raise ValueError("Model claim physical row is incomplete.")
        if self.kind == "structural_row" and (
            self.table_id is not None or self.row_index is not None
        ):
            raise ValueError("Structural row cannot invent table coordinates.")
        return self


class ModelClaimSupport(NativeModel):
    role: Literal["label", "currency", "date_context", "value_context", "continuation"]
    anchor: ModelClaimAnchor


class NativeMemberBinding(NativeModel):
    index: int = Field(ge=0, lt=3000, strict=True)
    pointer: str
    canonical_member_sha256: Sha256
    claim_id: Sha256

    @model_validator(mode="after")
    def exact_pointer(self) -> "NativeMemberBinding":
        if self.pointer != f"/extraction/claims/{self.index}":
            raise ValueError("Native member pointer is not its exact claim index.")
        return self


class NativeModelClaim(NativeModel):
    schema_version: Literal["native_model_claim.v1"] = "native_model_claim.v1"
    claim_id: Sha256
    claim_set_id: UUID
    document_id: UUID
    raw_member_json: dict[str, Any]
    proposed: ProposedClaim
    member: NativeMemberBinding
    anchor: ModelClaimAnchor
    supporting_anchors: tuple[ModelClaimSupport, ...] = Field(max_length=8)
    physical_row: ModelClaimRow | None
    physical_source_id: Sha256
    group_id: Sha256 | None
    source_engine: Literal["qwen3_8_27b"]
    derivation: Literal["model_emission"] = "model_emission"
    interpretation_origin: Literal["model_emission"] = "model_emission"
    configuration_sha256: Sha256
    checkpoint_sha256: Sha256
    invocation_request_id: UUID
    raw_output_sha256: Sha256
    interpretation_diagnostics: tuple[str, ...]
    requires_review: Literal[True] = True
    source_pixel_support: Literal["not_evaluated"] = "not_evaluated"

    @model_validator(mode="after")
    def recorded_member(self) -> "NativeModelClaim":
        if (
            canonical_digest(self.raw_member_json) != self.member.canonical_member_sha256
            or TypeAdapter(ProposedClaim).validate_python(self.raw_member_json) != self.proposed
            or self.anchor.source_text != self.proposed.raw_value
            or self.member.claim_id != self.claim_id
            or (self.physical_row is None) != (self.proposed.physical_row is None)
        ):
            raise ValueError("Native model claim does not match its recorded member.")
        physical = physical_identity(self.anchor, self.physical_row)
        if (
            self.physical_source_id != physical
            or self.group_id != (physical if self.physical_row is not None else None)
            or self.claim_id
            != claim_identity(self.claim_set_id, physical, self.proposed.canonical_key)
        ):
            raise ValueError("Native model claim physical identity is inconsistent.")
        if len(self.supporting_anchors) != len(self.proposed.supporting_sources):
            raise ValueError("Native model claim support inventory is incomplete.")
        for bound, raw in zip(
            self.supporting_anchors, self.proposed.supporting_sources, strict=True
        ):
            if bound.role != raw.role or bound.anchor.source_text != raw.quote:
                raise ValueError("Native model claim support differs from its recorded quote.")
        return self

    @property
    def fingerprint(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))
