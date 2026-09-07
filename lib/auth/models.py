from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from lib.contracts import SessionInfo


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class BootstrapResult:
    household_id: UUID
    user_id: UUID
    email: str


@dataclass(frozen=True)
class CreatedSession:
    token: str
    csrf_token: str
    session: SessionInfo


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: UUID
    household_id: UUID | None
    email: str
    display_name: str
    auth_method: str
    household_role: str | None = None
    session_id: UUID | None = None
    api_token_id: UUID | None = None
    scopes: tuple[str, ...] = ()
    csrf_token_hash: str | None = field(default=None, repr=False)
