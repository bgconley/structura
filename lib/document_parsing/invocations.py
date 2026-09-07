"""Explicit invocation versions; historical v1 serialization is immutable."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ParseInvocation(BaseModel):
    # Preserve v1's original fields, defaults, order and model configuration.
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    request_id: UUID
    page_numbers: tuple[Annotated[int, Field(gt=0)], ...]
    profile: str
    served_model: str
    source_engine: str
    prompt_version: str
    output_schema_version: str
    raw_output_sha256: Digest
    finish_reason: str | None
    latency_ms: int = Field(ge=0)


class ParseInvocationV2(ParseInvocation):
    invocation_version: Literal["structura.parse_invocation.v2"]
    # Both models are frozen; narrowing this immutable field is intentional.
    output_schema_version: Literal["structura.page_understanding.v2"]  # pyright: ignore[reportIncompatibleVariableOverride]
    configuration_sha256: Digest
    source_inventory_sha256: Digest
    context_sha256: Digest
    prompt_sha256: Digest
    output_schema_sha256: Digest
    request_sha256: Digest
    reported_model_version: str | None = Field(min_length=1, max_length=300)


def decode_parse_invocation(value: Any) -> ParseInvocation | ParseInvocationV2:
    payload = value.model_dump(mode="json") if isinstance(value, ParseInvocation) else value
    if not isinstance(payload, dict):
        raise ValueError("Invocation must be an explicit supported version.")
    version = payload.get("output_schema_version")
    if version == "structura.page_parse.v1":
        return ParseInvocation.model_validate(payload)
    if version == "structura.page_understanding.v2":
        return ParseInvocationV2.model_validate(payload)
    raise ValueError("Invocation output version is unsupported.")


AnyParseInvocation = Annotated[
    ParseInvocationV2 | ParseInvocation,
    BeforeValidator(decode_parse_invocation),
    Field(json_schema_extra=lambda schema: _explicit_versions(schema)),
]


def _explicit_versions(schema: dict[str, Any]) -> None:
    # The old model remains unchanged. Its permissive string field must not let
    # a union's JSON schema accept unknown versions that the runtime rejects.
    branches = schema["anyOf"]
    schema["anyOf"] = [
        {"allOf": [branch, {"properties": {"output_schema_version": {"const": version}}}]}
        for branch, version in zip(
            branches, ("structura.page_understanding.v2", "structura.page_parse.v1"), strict=True
        )
    ]
