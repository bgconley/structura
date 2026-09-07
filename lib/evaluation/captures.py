"""Captured neutral parse records; no database access or inferred model execution."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from lib.document_parsing.structure import DocumentStructure
from lib.document_processing.models import ParseConfiguration
from lib.evaluation.identity import Digest, EvaluationModel, Label


class CapturedRawPage(EvaluationModel):
    request_id: UUID
    page_number: int = Field(ge=1)
    raw_output: str = Field(max_length=2000000)


class DocumentCapture(EvaluationModel):
    schema_version: Literal["structura.parse_capture.v1"] = "structura.parse_capture.v1"
    item_id: Label
    fixture_type: Literal["deterministic_fixture", "model_backed"]
    model_mode: Literal["fixture", "live", "required"]
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    configuration: ParseConfiguration
    configuration_sha256: Digest
    max_output_tokens: int = Field(ge=1)
    temperature: float = Field(ge=0, le=2)
    structure: DocumentStructure
    raw_pages: tuple[CapturedRawPage, ...] = Field(max_length=500)

    @model_validator(mode="after")
    def consistent_mode(self) -> DocumentCapture:
        if (self.fixture_type == "deterministic_fixture") != (self.model_mode == "fixture"):
            raise ValueError("Fixture captures cannot claim live model mode.")
        return self
