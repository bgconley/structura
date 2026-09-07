"""Requests, receipts and safe errors shared by document intake adapters."""

from dataclasses import dataclass
from uuid import UUID

from lib.contracts import AcceptedJob


@dataclass(frozen=True)
class DocumentIngestionRequest:
    household_id: UUID
    owner_user_id: UUID
    source: str
    filename: str | None
    declared_mime_type: str | None = None
    supplied_title: str | None = None
    hints: dict[str, object] | None = None
    requested_by: str = "user"


@dataclass(frozen=True)
class DocumentIngestionResult:
    accepted_job: AcceptedJob
    document_id: UUID
    asset_id: UUID
    sha256: str


class DocumentIngestionError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
