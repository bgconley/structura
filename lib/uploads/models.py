"""Public upload commands/observations and private immutable transfer identities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from lib.auth.request_authority import RequestCredential

UploadState = Literal[
    "awaiting_content",
    "receiving",
    "awaiting_duplicate_decision",
    "accepted",
    "reused",
    "rejected",
    "cancelled",
    "expired",
]


class UploadModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", populate_by_name=True, alias_generator=to_camel
    )


class UploadCreate(UploadModel):
    operation_id: UUID
    client_batch_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    declared_bytes: int = Field(gt=0, le=100 * 1024 * 1024, strict=True)
    declared_mime_type: str | None = Field(default=None, max_length=150)
    source: Literal["web_upload", "api_upload", "mobile_scan", "bulk_import"] = "web_upload"
    title: str | None = Field(default=None, max_length=500)


class UploadDecision(UploadModel):
    revision: UUID
    decision: Literal["keep_separate", "use_existing"]
    document_id: UUID | None = None

    @model_validator(mode="after")
    def exact_choice(self) -> UploadDecision:
        if (self.decision == "use_existing") != (self.document_id is not None):
            raise ValueError("Only use_existing requires an exact document ID.")
        return self


class UploadReceipt(UploadModel):
    outcome: Literal["accepted", "reused"]
    document_id: UUID
    asset_id: UUID
    batch_id: UUID | None = None
    job_id: UUID | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(gt=0)
    # Time this operation committed, not the original document's acceptance time.
    recorded_at: datetime


class UploadDuplicate(UploadModel):
    document_id: UUID
    title: str


class UploadFailure(UploadModel):
    code: str
    message: str


class UploadAttempt(UploadModel):
    upload_id: UUID
    operation_id: UUID
    client_batch_id: UUID
    revision: UUID
    state: UploadState
    filename: str
    declared_bytes: int
    actual_bytes: int | None = None
    sha256: str | None = None
    detected_mime_type: str | None = None
    current_transfer_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    receipt: UploadReceipt | None = None
    error: UploadFailure | None = None
    duplicates: tuple[UploadDuplicate, ...] = ()


@dataclass(frozen=True)
class TransferLease:
    upload_id: UUID
    transfer_id: UUID
    generation: int
    owner_token: UUID
    credential: RequestCredential
    metadata: UploadCreate
    kind: Literal["receive", "replay", "decision"]
    source_transfer_id: UUID
    deadline_at: datetime


@dataclass(frozen=True)
class VerifiedContent:
    sha256: str
    byte_size: int
    mime_type: str
