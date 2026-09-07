"""Versioned frozen parser intent; v1 fields/defaults remain defined unchanged."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field

from lib.document_parsing.document_context import FrozenDocumentContext
from lib.document_parsing.structure import Sha256, StructureModel
from lib.document_processing.models import ParseConfiguration


class ParseRequestSettings(StructureModel):
    # Every field is required. A null seed means deliberately omit it from HTTP;
    # this is distinct from an explicit zero seed and is included in identity.
    max_output_tokens: int = Field(ge=1, le=32768, strict=True)
    temperature: float = Field(ge=0, le=2)
    seed: int | None = Field(ge=0, le=2147483647, strict=True)
    timeout_seconds: int = Field(ge=1, le=600, strict=True)


class UnderstandingDefinitions(StructureModel):
    output_version: Literal["structura.page_understanding.v2"]
    taxonomy_version: str = Field(min_length=1, max_length=100)
    registry_version: str = Field(min_length=1, max_length=100)
    typing_version: str = Field(min_length=1, max_length=100)
    schema_sha256: Sha256
    taxonomy_sha256: Sha256
    registry_sha256: Sha256
    typing_sha256: Sha256
    validation_sha256: Sha256


class ParseConfigurationV2(ParseConfiguration):
    configuration_version: Literal["structura.parse_configuration.v2"]
    # Both models are frozen; narrowing this immutable field is intentional.
    output_schema_version: Literal["structura.page_understanding.v2"]  # pyright: ignore[reportIncompatibleVariableOverride]
    definitions: UnderstandingDefinitions
    profile_sha256: Sha256
    prompt_template_sha256: Sha256
    request_builder_sha256: Sha256
    context_recipe_sha256: Sha256
    normalizer_sha256: Sha256
    context: FrozenDocumentContext
    request: ParseRequestSettings


def decode_parse_configuration(value: Any) -> ParseConfiguration | ParseConfigurationV2:
    payload = value.model_dump(mode="json") if isinstance(value, ParseConfiguration) else value
    if not isinstance(payload, dict):
        raise ValueError("Parser configuration must have an explicit supported output version.")
    version = payload.get("output_schema_version")
    if version == "structura.page_parse.v1":
        return ParseConfiguration.model_validate(payload)
    if version == "structura.page_understanding.v2":
        return ParseConfigurationV2.model_validate(payload)
    raise ValueError("Parser configuration output version is unsupported.")


AnyParseConfiguration = Annotated[
    ParseConfigurationV2 | ParseConfiguration,
    BeforeValidator(decode_parse_configuration),
    Field(json_schema_extra=lambda schema: _explicit_versions(schema)),
]


def _explicit_versions(schema: dict[str, Any]) -> None:
    branches = schema["anyOf"]
    schema["anyOf"] = [
        {"allOf": [branch, {"properties": {"output_schema_version": {"const": version}}}]}
        for branch, version in zip(
            branches, ("structura.page_understanding.v2", "structura.page_parse.v1"), strict=True
        )
    ]
