"""Immutable identity of a synchronous request, not a durable worker authority.

Capture only after the normal authentication and unsafe-request CSRF dependencies
have succeeded. Persist this identity across byte IO; never replace its credential
with a later request's cookie without an explicit new admission/lease.
"""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from lib.auth.authorization_policy import AuthorizationError
from lib.auth.models import AuthPrincipal


@dataclass(frozen=True)
class RequestCredential:
    user_id: UUID
    household_id: UUID
    kind: Literal["session", "api_token"]
    session_id: UUID | None
    api_token_id: UUID | None
    scope_ceiling: tuple[str, ...] = ()
    session_csrf_bound: bool = False

    def __post_init__(self) -> None:
        session = (
            self.kind == "session"
            and self.session_id is not None
            and self.api_token_id is None
            and self.session_csrf_bound
            and not self.scope_ceiling
        )
        token = (
            self.kind == "api_token"
            and self.api_token_id is not None
            and self.session_id is None
            and not self.session_csrf_bound
        )
        if not (session or token):
            raise AuthorizationError("Permission denied")

    @classmethod
    def from_principal(cls, principal: AuthPrincipal) -> "RequestCredential":
        if principal.household_id is None:
            raise AuthorizationError("Permission denied")
        if principal.auth_method == "api_token":
            return cls(
                principal.user_id,
                principal.household_id,
                "api_token",
                principal.session_id,
                principal.api_token_id,
                tuple(sorted(set(principal.scopes))),
            )
        if principal.auth_method not in {"password", "magic_link", "passkey"}:
            raise AuthorizationError("Permission denied")
        return cls(
            principal.user_id,
            principal.household_id,
            "session",
            principal.session_id,
            principal.api_token_id,
            session_csrf_bound=principal.csrf_token_hash is not None,
        )
