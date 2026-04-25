from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from lib.auth import AuthPrincipal, AuthService
from lib.config import get_settings

ADMIN_HOUSEHOLD_ROLES = {"owner", "admin"}
ADMIN_API_SCOPES = {"admin", "admin:*", "jobs:admin", "service:admin"}


def auth_service() -> AuthService:
    return AuthService()


def session_cookie_value(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


def current_principal(
    request: Request,
    x_api_token: Annotated[str | None, Header(alias="X-API-Token")] = None,
) -> AuthPrincipal:
    service = AuthService()
    if x_api_token:
        principal = service.resolve_api_token(x_api_token)
        if principal:
            return principal
    structura_session = session_cookie_value(request)
    if structura_session:
        principal = service.resolve_session_token(structura_session)
        if principal:
            request.state.session_token = structura_session
            return principal
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def require_csrf(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthPrincipal:
    if principal.api_token_id:
        return principal
    settings = get_settings()
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    if not csrf_cookie or not x_csrf_token or csrf_cookie != x_csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token required")
    return principal


def require_admin(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> AuthPrincipal:
    if principal.household_id and principal.household_role in ADMIN_HOUSEHOLD_ROLES:
        return principal
    if (
        principal.household_id
        and principal.api_token_id
        and ADMIN_API_SCOPES.intersection(principal.scopes)
    ):
        return principal
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


def require_admin_csrf(
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> AuthPrincipal:
    if principal.household_id and principal.household_role in ADMIN_HOUSEHOLD_ROLES:
        return principal
    if (
        principal.household_id
        and principal.api_token_id
        and ADMIN_API_SCOPES.intersection(principal.scopes)
    ):
        return principal
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
