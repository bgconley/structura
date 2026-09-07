"""Immutable candidate input, source and checkpoint contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lib.document_parsing.structure import Sha256, SourceRender, TextOrigin
from lib.document_processing.models import ProcessingBinding, content_digest
from lib.search.indexing.configuration import Modality


class IndexModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


@dataclass(frozen=True)
class IndexBinding:
    processing: ProcessingBinding
    index_generation_id: UUID


class IndexRenderAsset(IndexModel):
    id: UUID
    page_id: UUID
    page_number: int = Field(gt=0, le=500)
    source: SourceRender
    uri: str = Field(min_length=1, max_length=1000)
    mime_type: Literal["image/png"] = "image/png"
    byte_size: int = Field(gt=0, le=10 * 1024 * 1024)


class IndexInput(IndexModel):
    id: UUID
    ordinal: int = Field(ge=0)
    modality: Modality
    owner_id: UUID
    page_number: int = Field(gt=0, le=500)
    element_ids: tuple[UUID, ...]
    text: str
    text_origins: tuple[TextOrigin, ...]
    render_asset_id: UUID | None
    content_sha256: Sha256
    model_input_sha256: Sha256
    purpose: Literal["document"] = "document"
    identity_scheme: Literal["model-input-v1"] = "model-input-v1"


class PageDisposition(IndexModel):
    page_number: int = Field(gt=0, le=500)
    text: Literal["eligible", "ineligible", "not_requested"]
    visual: Literal["eligible", "ineligible", "not_requested"]
    text_reason: Literal["nonempty_chunks", "no_text", "not_requested"]
    visual_reasons: tuple[
        Literal[
            "image_original",
            "low_native_text",
            "layout_complexity",
            "partial_parse",
            "digital_text_page",
            "not_requested",
        ],
        ...,
    ]
    parse_state: Literal["processed", "partial", "insufficient_signal"]
    whitespace_chunk_ids: tuple[UUID, ...] = ()


class CandidateIndexEvent(IndexModel):
    """Reserved explicit binding for a later candidate worker; not a legacy job."""

    schema_version: Literal["structura.native_index_job.v1"] = "structura.native_index_job.v1"
    document_id: UUID
    processing_run_id: UUID
    parse_generation_id: UUID
    index_generation_id: UUID
    configuration_sha256: Sha256


class IndexManifest(IndexModel):
    schema_version: Literal["structura.native_index_manifest.v1"] = (
        "structura.native_index_manifest.v1"
    )
    index_generation_id: UUID
    parse_generation_id: UUID
    structure_sha256: Sha256
    configuration_sha256: Sha256
    inputs: tuple[IndexInput, ...] = Field(max_length=4096)
    pages: tuple[PageDisposition, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def ordered_unique_inventory(self) -> IndexManifest:
        if tuple(item.ordinal for item in self.inputs) != tuple(range(len(self.inputs))):
            raise ValueError("Candidate inputs must have complete ordered ordinals.")
        if len({item.id for item in self.inputs}) != len(self.inputs):
            raise ValueError("Candidate input identities must be unique.")
        if tuple(page.page_number for page in self.pages) != tuple(range(1, len(self.pages) + 1)):
            raise ValueError("Candidate page inventory must be complete and ordered.")
        return self

    @property
    def fingerprint(self) -> str:
        return content_digest(self.model_dump(mode="json"))


class VectorObservation(IndexModel):
    input_id: UUID
    model_input_sha256: Sha256
    values: tuple[float, ...]
    profile: str
    reported_model: str
    reported_model_version: str = Field(default="", max_length=200)
    declared_artifact_revision: str
    identity_source: Literal["reported_model"] = "reported_model"
    model_mode: Literal["live", "fixture"]
    invocation_id: UUID
    latency_ms: int = Field(ge=0)

    @field_validator("values", mode="before")
    @classmethod
    def strict_numbers(cls, value: object) -> object:
        if not isinstance(value, list | tuple) or any(type(v) not in {int, float} for v in value):
            raise ValueError("Vector coordinates must be numbers, without coercion.")
        return value
