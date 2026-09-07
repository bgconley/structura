from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from lib.contracts import JobState


@dataclass(frozen=True)
class QueueTransportProfile:
    requested: str
    active: str
    reason: str | None = None


@dataclass(frozen=True)
class ClaimedJob:
    state: JobState
    payload: dict[str, Any]
    document_id: UUID | None
    household_id: UUID | None
    claim_token: UUID
    lease_expires_at: datetime
    attempt_count: int
    max_attempts: int
    processing_run_id: UUID | None = None
    parse_generation_id: UUID | None = None


@dataclass(frozen=True)
class BulkCancelResult:
    cancelled_job_ids: tuple[UUID, ...]
    skipped_job_ids: tuple[UUID, ...]

    @property
    def cancelled_count(self) -> int:
        return len(self.cancelled_job_ids)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_job_ids)
