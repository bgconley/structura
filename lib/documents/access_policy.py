from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DocumentAccessContext:
    household_id: UUID
    user_id: UUID
    household_role: str | None = None


def document_read_access_params(access: DocumentAccessContext) -> tuple[object, ...]:
    return (
        access.household_id,
        access.user_id,
        access.household_role,
    )
