"""Immutable parse-owned source catalog and exact-generation response contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.document_parsing.structure import (
    Sha256,
    SourcePage,
    SourceRender,
    StructureChunk,
    StructurePage,
)
from lib.document_processing.configuration_types import AnyParseConfiguration
from lib.document_processing.models import ProcessingBinding, content_digest

MAX_RENDER_BYTES = 128 * 1024 * 1024
MAX_RENDER_PIXELS = 40_000_000


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class RasterIdentity(EvidenceModel):
    image_sha256: Sha256
    pixel_width: int = Field(gt=0)
    pixel_height: int = Field(gt=0)
    renderer: str = Field(min_length=1)
    renderer_version: str = Field(min_length=1)
    coordinate_space: Literal["rendered_source_pixels"] = "rendered_source_pixels"

    @model_validator(mode="after")
    def bounded_pixels(self) -> RasterIdentity:
        if self.pixel_width * self.pixel_height > MAX_RENDER_PIXELS:
            raise ValueError("Source raster exceeds the retained pixel bound.")
        return self

    @classmethod
    def from_source(cls, source: SourceRender) -> RasterIdentity:
        return cls.model_validate(
            source.model_dump(exclude={"page_number", "native_text", "native_text_origin"})
        )


class ExpectedPage(EvidenceModel):
    page_number: int = Field(gt=0, le=500)
    page_id: UUID
    checkpoint_sha256: Sha256
    source_render_sha256: Sha256
    render: RasterIdentity


class ExpectedRenderSet(EvidenceModel):
    schema_version: Literal["structura.retained_render_set.v1"] = "structura.retained_render_set.v1"
    document_id: UUID
    processing_run_id: UUID
    parse_generation_id: UUID
    original_asset_id: UUID
    original_sha256: Sha256
    inventory_sha256: Sha256
    structure_sha256: Sha256
    parse_configuration_sha256: Sha256
    pages: tuple[ExpectedPage, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def complete_inventory(self) -> ExpectedRenderSet:
        if tuple(p.page_number for p in self.pages) != tuple(range(1, len(self.pages) + 1)):
            raise ValueError("Retained pages must have complete ordered ordinals.")
        if len({p.page_id for p in self.pages}) != len(self.pages):
            raise ValueError("Retained page IDs must be unique.")
        return self

    @property
    def fingerprint(self) -> str:
        return content_digest(self.model_dump(mode="json"))


@dataclass(frozen=True)
class RenderSetBinding:
    processing: ProcessingBinding
    render_set_id: UUID


def render_set_id(parse_id: UUID) -> UUID:
    return uuid5(parse_id, "retained-source-render-set-v1")


def source_render_id(parse_id: UUID, page_id: UUID) -> UUID:
    return uuid5(parse_id, f"source-render-v1:{page_id}")


class RetainedPageAsset(EvidenceModel):
    id: UUID
    page_number: int = Field(gt=0, le=500)
    page_id: UUID
    checkpoint_sha256: Sha256
    source_render_sha256: Sha256
    render: RasterIdentity
    uri: str = Field(min_length=1, max_length=1000)
    byte_size: int = Field(gt=0, le=MAX_RENDER_BYTES)
    mime_type: Literal["image/png"] = "image/png"

    @property
    def fingerprint(self) -> str:
        return content_digest(self.model_dump(mode="json"))


@dataclass(frozen=True)
class RetainedRenderProgress:
    state: Literal["pending", "sealed"]
    render_set_id: UUID
    expected_sha256: str
    completion_sha256: str | None
    completed_page_ids: tuple[UUID, ...]
    remaining_page_ids: tuple[UUID, ...]
    new_pages: int
    new_bytes: int


@dataclass(frozen=True)
class RenderSetSnapshot:
    expected: ExpectedRenderSet
    assets: tuple[RetainedPageAsset, ...]
    state: Literal["building", "sealed"]
    completion_sha256: str | None


class GenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class GenerationEvidenceRender(GenerationResponse):
    id: UUID
    image_url: str = Field(alias="imageUrl")
    sha256: Sha256
    byte_size: int = Field(alias="byteSize", gt=0, le=MAX_RENDER_BYTES)
    pixel_width: int = Field(alias="pixelWidth", gt=0)
    pixel_height: int = Field(alias="pixelHeight", gt=0)
    coordinate_space: Literal["rendered_source_pixels"] = Field(
        default="rendered_source_pixels", alias="coordinateSpace"
    )


class GenerationEvidencePageSummary(GenerationResponse):
    page_id: UUID = Field(alias="pageId")
    page_number: int = Field(alias="pageNumber", gt=0, le=500)
    source_page: SourcePage = Field(alias="sourcePage")
    parse_state: Literal["processed", "partial", "insufficient_signal"] = Field(alias="parseState")
    render_registration: Literal["registered", "not_retained"] = Field(alias="renderRegistration")
    render: GenerationEvidenceRender | None = None


class GenerationEvidenceManifest(GenerationResponse):
    document_id: UUID = Field(alias="documentId")
    processing_run_id: UUID = Field(alias="processingRunId")
    parse_generation_id: UUID = Field(alias="parseGenerationId")
    view_scope: Literal["retained_parse_generation"] = Field(
        default="retained_parse_generation", alias="viewScope"
    )
    processing_run_state: Literal["sealed", "superseded", "cancelled"] = Field(
        alias="processingRunState"
    )
    parser_configuration: AnyParseConfiguration = Field(alias="parserConfiguration")
    transcription_authority: Literal["derived_source_transcription"] = Field(
        default="derived_source_transcription", alias="transcriptionAuthority"
    )
    original_asset_id: UUID = Field(alias="originalAssetId")
    original_sha256: Sha256 = Field(alias="originalSha256")
    structure_sha256: Sha256 = Field(alias="structureSha256")
    inventory_sha256: Sha256 = Field(alias="inventorySha256")
    render_set_state: Literal["building", "sealed"] | None = Field(alias="renderSetState")
    render_set_sha256: Sha256 | None = Field(alias="renderSetSha256")
    total: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    pages: list[GenerationEvidencePageSummary]
    observed_at: datetime = Field(alias="observedAt")


class GenerationEvidencePage(GenerationResponse):
    document_id: UUID = Field(alias="documentId")
    processing_run_id: UUID = Field(alias="processingRunId")
    parse_generation_id: UUID = Field(alias="parseGenerationId")
    view_scope: Literal["retained_parse_generation"] = Field(
        default="retained_parse_generation", alias="viewScope"
    )
    source_page: SourcePage = Field(alias="sourcePage")
    page: StructurePage
    chunks: tuple[StructureChunk, ...]
    render: GenerationEvidenceRender | None
