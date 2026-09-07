"""Principal capability limits; persisted resource grants are checked by repositories."""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

Action = Literal[
    "documents:read", "documents:write", "documents:review", "jobs:admin", "service:admin"
]


class AuthorizationSubject(Protocol):
    @property
    def household_id(self) -> UUID | None: ...

    @property
    def household_role(self) -> str | None: ...

    @property
    def api_token_id(self) -> UUID | None: ...

    @property
    def scopes(self) -> tuple[str, ...]: ...


class AuthorizationError(Exception):
    """The authenticated principal does not have the requested capability."""


_ACTION_SCOPES: dict[Action, frozenset[str]] = {
    "documents:read": frozenset({"documents:read", "documents:write", "documents:review"}),
    "documents:write": frozenset({"documents:write"}),
    "documents:review": frozenset({"documents:review", "documents:write"}),
    "jobs:admin": frozenset({"jobs:admin"}),
    "service:admin": frozenset({"service:admin"}),
}


def permits_action(subject: AuthorizationSubject, action: Action) -> bool:
    if not subject.household_id:
        return False
    if action in {"jobs:admin", "service:admin"}:
        roles = {"owner", "admin"}
    elif action == "documents:read":
        roles = {"owner", "admin", "member", "viewer"}
    else:
        roles = {"owner", "admin", "member"}
    if subject.household_role not in roles:
        return False
    if subject.api_token_id is None:
        return True
    return bool(set(subject.scopes) & (_ACTION_SCOPES[action] | {"admin", "admin:*"}))


def require_action(subject: AuthorizationSubject, action: Action) -> None:
    if not permits_action(subject, action):
        raise AuthorizationError("Permission denied")
