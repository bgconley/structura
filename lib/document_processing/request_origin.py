"""Explicit authenticated request origin, separate from a worker's execution lease."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from lib.auth.authorization_policy import scopes_permit_action
from lib.auth.models import AuthPrincipal
from lib.document_processing.errors import ProcessingError


@dataclass(frozen=True)
class ProcessingOrigin:
    user_id: UUID
    household_id: UUID
    kind: Literal["session", "api_token"]
    session_id: UUID | None
    api_token_id: UUID | None
    scope_ceiling: tuple[str, ...] = ()

    @classmethod
    def from_principal(cls, principal: AuthPrincipal) -> ProcessingOrigin:
        if principal.household_id is None:
            raise ProcessingError("Processing requires an authenticated household origin.")
        if (
            principal.auth_method == "api_token"
            and principal.api_token_id is not None
            and principal.session_id is None
            and scopes_permit_action(principal.scopes, "documents:write")
        ):
            return cls(
                principal.user_id,
                principal.household_id,
                "api_token",
                None,
                principal.api_token_id,
                tuple(sorted(set(principal.scopes))),
            )
        if (
            principal.auth_method in {"password", "magic_link", "passkey"}
            and principal.session_id is not None
            and principal.api_token_id is None
        ):
            return cls(
                principal.user_id, principal.household_id, "session", principal.session_id, None
            )
        raise ProcessingError("Processing requires an authenticated write-capable origin.")
