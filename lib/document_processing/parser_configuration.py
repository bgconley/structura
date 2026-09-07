"""Reproducible native-parser configuration and explicit deployment declarations.

A served alias identifies a response route, not a verified checkpoint revision.
The caller's declaration is recorded as such; fixture output stays identifiable
in 096's existing model_revision field without changing its frozen schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lib.document_parsing.normalization import NORMALIZER_VERSION
from lib.document_parsing.qwen_page_parser import OUTPUT_SCHEMA_VERSION, PROMPT_VERSION
from lib.document_parsing.searchable_text import CHUNKER_VERSION
from lib.document_parsing.source_adapter import renderer_identity
from lib.document_parsing.structure import SourceMediaType
from lib.document_processing.errors import ProcessingError
from lib.document_processing.models import ParseConfiguration
from lib.model_runtime.profiles import QWEN_INGESTION_PROFILE, get_model_profile


class DeclaredParserDeployment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["live", "fixture"]
    served_model: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=180)

    @property
    def recorded_revision(self) -> str:
        prefix = "declared-live" if self.mode == "live" else "fixture"
        return f"{prefix}:{self.revision}"


def parser_configuration(
    deployment: DeclaredParserDeployment,
    mime_type: SourceMediaType,
    *,
    render_scale: float = 2,
) -> ParseConfiguration:
    """Freeze installed parser/render versions before requesting an authorized run."""
    profile = get_model_profile(QWEN_INGESTION_PROFILE)
    if deployment.served_model != profile.served_model_name:
        raise ProcessingError("Parser deployment does not match the accepted ingestion profile.")
    if not deployment.revision.strip() or deployment.revision.strip() in {
        deployment.served_model,
        profile.name,
        profile.base_model,
    }:
        raise ProcessingError("Parser deployment requires an explicit revision declaration.")
    renderer, renderer_version = renderer_identity(mime_type)
    return ParseConfiguration(
        profile=profile.name,
        served_model=deployment.served_model,
        source_engine=profile.source_engine,
        model_revision=deployment.recorded_revision,
        prompt_version=PROMPT_VERSION,
        output_schema_version=OUTPUT_SCHEMA_VERSION,
        normalizer_version=NORMALIZER_VERSION,
        chunker_version=CHUNKER_VERSION,
        renderer=renderer,
        renderer_version=renderer_version,
        render_scale=render_scale,
    )


def validate_parser_configuration(
    frozen: ParseConfiguration,
    deployment: DeclaredParserDeployment,
    mime_type: SourceMediaType,
) -> None:
    actual = parser_configuration(deployment, mime_type, render_scale=frozen.render_scale)
    if frozen != actual:
        raise ProcessingError(
            "Frozen parser configuration does not match this executor deployment."
        )
