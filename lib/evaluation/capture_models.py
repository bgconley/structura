"""Exact-generation capture requests and explicit verification boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from lib.document_parsing.structure import SourceMediaType
from lib.evaluation.captures import DocumentCapture
from lib.evaluation.identity import Digest, EvaluationModel, Label


class CaptureUnavailable(Exception):
    """No readable sealed generation matches the requested identity."""


class CaptureIntegrityError(Exception):
    """Stored generation evidence is inconsistent or unsupported."""


class CaptureDeclaration(EvaluationModel):
    item_id: Label
    commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    max_output_tokens: int = Field(ge=1)
    temperature: float = Field(ge=0, le=2)


class RegisteredCaptureSource(EvaluationModel):
    original_asset_id: UUID
    original_sha256: Digest
    mime_type: SourceMediaType
    byte_size: int = Field(gt=0, le=100 * 1024 * 1024)


@dataclass(frozen=True)
class PersistedGenerationCapture:
    capture: DocumentCapture
    document_id: UUID
    run_status: Literal["sealed", "superseded", "cancelled"]
    sealed_at: datetime
    structure_sha256: str
    inventory_sha256: str
    source: RegisteredCaptureSource
    storage_integrity: Literal["verified"] = "verified"
    commit_provenance: Literal["externally_declared"] = "externally_declared"
    generation_settings_provenance: Literal["externally_declared"] = "externally_declared"
    invocation_authenticity: Literal["not_evaluated"] = "not_evaluated"
    original_artifact_verification: Literal["not_evaluated"] = "not_evaluated"
    rendered_artifact_verification: Literal["not_evaluated"] = "not_evaluated"
