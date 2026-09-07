"""Freeze the accepted embedding spaces and bounded native projection policy."""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.document_processing.models import content_digest
from lib.model_runtime.embedding_protocol import VISUAL_SYSTEM_INSTRUCTION, EmbeddingProtocol
from lib.model_runtime.profiles import (
    TEXT_EMBED_BLACKBIRD_PROFILE,
    VISUAL_EMBED_BLACKBIRD_PROFILE,
    get_model_profile,
)

Modality = Literal["text", "visual"]


class FrozenModelSpace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: str
    base_model: str
    served_model: str
    dimensions: Literal[1536, 2048]
    modality: Modality
    metric: Literal["cosine"] = "cosine"
    protocol: EmbeddingProtocol
    visual_system_instruction: str | None


def accepted_space(modality: Modality) -> FrozenModelSpace:
    name = TEXT_EMBED_BLACKBIRD_PROFILE if modality == "text" else VISUAL_EMBED_BLACKBIRD_PROFILE
    profile = get_model_profile(name)
    return FrozenModelSpace.model_validate(
        dict(
            profile=name,
            base_model=profile.base_model,
            served_model=profile.served_model_name,
            dimensions=profile.output_dimensions,
            modality=modality,
            protocol=asdict(profile.embedding_protocol) if profile.embedding_protocol else None,
            visual_system_instruction=VISUAL_SYSTEM_INSTRUCTION if modality == "visual" else None,
        )
    )


class IndexConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    schema_version: Literal["structura.native_index_configuration.v1"] = (
        "structura.native_index_configuration.v1"
    )
    model_mode: Literal["live", "fixture"]
    modalities: tuple[Modality, ...] = ("text", "visual")
    spaces: tuple[FrozenModelSpace, ...]
    projection_version: Literal["native_parse_only_v1"] = "native_parse_only_v1"
    visual_policy: Literal["native_visual_eligibility_v1"] = "native_visual_eligibility_v1"
    input_identity_scheme: Literal["model-input-v1"] = "model-input-v1"
    fact_basis: Literal["not_collected"] = "not_collected"
    metadata_basis: Literal["not_collected"] = "not_collected"
    max_text_bytes: int = Field(default=6000, gt=0, le=6000)
    max_inputs: int = Field(default=4096, gt=0, le=4096)

    @model_validator(mode="after")
    def exact_spaces(self) -> IndexConfiguration:
        ordered_modalities: tuple[Modality, ...] = ("text", "visual")
        expected = tuple(modality for modality in ordered_modalities if modality in self.modalities)
        if not expected or self.modalities != expected:
            raise ValueError("Candidate modalities must be distinct and ordered.")
        if self.spaces != tuple(accepted_space(cast(Modality, modality)) for modality in expected):
            raise ValueError("Candidate model spaces must match the accepted profiles exactly.")
        return self

    @property
    def fingerprint(self) -> str:
        return content_digest(self.model_dump(mode="json"))

    def space(self, modality: Modality) -> FrozenModelSpace:
        return next(space for space in self.spaces if space.modality == modality)


def index_configuration(
    *, model_mode: Literal["live", "fixture"], modalities: tuple[Modality, ...] = ("text", "visual")
) -> IndexConfiguration:
    return IndexConfiguration(
        model_mode=model_mode,
        modalities=modalities,
        spaces=tuple(accepted_space(m) for m in modalities),
    )
