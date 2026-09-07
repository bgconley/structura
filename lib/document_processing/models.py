"""Explicit processing identities and reproducible parser configuration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ParseConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    profile: str = Field(min_length=1, max_length=200)
    served_model: str = Field(min_length=1, max_length=200)
    source_engine: str = Field(min_length=1, max_length=100)
    model_revision: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=100)
    output_schema_version: str = Field(min_length=1, max_length=100)
    normalizer_version: str = Field(min_length=1, max_length=100)
    chunker_version: str = Field(min_length=1, max_length=100)
    renderer: str = Field(min_length=1, max_length=100)
    renderer_version: str = Field(min_length=1, max_length=100)
    render_scale: float = Field(gt=0, le=4)

    @property
    def fingerprint(self) -> str:
        return content_digest(self.model_dump(mode="json"))


@dataclass(frozen=True)
class ProcessingBinding:
    document_id: UUID
    processing_run_id: UUID
    parse_generation_id: UUID


@dataclass(frozen=True)
class ProcessingRun:
    binding: ProcessingBinding
    household_id: UUID
    generation: int
    root_job_id: UUID
    status: str


def content_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()
