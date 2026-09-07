from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lib.auth.authorization_policy import permits_action


@dataclass(frozen=True)
class DocumentAccessContext:
    household_id: UUID
    user_id: UUID
    household_role: str | None = None
    api_token_id: UUID | None = None
    scopes: tuple[str, ...] = ()


def document_read_access_params(access: DocumentAccessContext) -> tuple[object, ...]:
    if access.api_token_id and not permits_action(access, "documents:read"):
        return (access.household_id, None, None)
    return (
        access.household_id,
        access.user_id,
        access.household_role,
    )


def document_write_access_params(access: DocumentAccessContext) -> tuple[object, ...]:
    """Fail closed for a limited token even when a repository is called directly."""
    if access.api_token_id and not permits_action(access, "documents:write"):
        return (access.household_id, None, None)
    return document_read_access_params(access)


def document_review_access_params(access: DocumentAccessContext) -> tuple[object, ...]:
    if access.api_token_id and not permits_action(access, "documents:review"):
        return (access.household_id, None, None)
    return document_read_access_params(access)
