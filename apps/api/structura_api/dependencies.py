from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from lib.auth import AuthPrincipal, AuthService
from lib.auth.authorization_policy import Action, permits_action
from lib.config import get_settings


def auth_service() -> AuthService:
    return AuthService()


def session_cookie_value(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


def current_principal(
    request: Request,
    x_api_token: Annotated[str | None, Header(alias="X-API-Token")] = None,
) -> AuthPrincipal:
    service = AuthService()
    if x_api_token is not None:
        principal = service.resolve_api_token(x_api_token)
        if principal:
            return principal
        raise HTTPException(status_code=401, detail="Not authenticated")
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


def _require_capability(principal: AuthPrincipal, action: Action) -> AuthPrincipal:
    if not permits_action(principal, action):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    return principal


def require_document_read(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> AuthPrincipal:
    return _require_capability(principal, "documents:read")


def require_document_write(
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> AuthPrincipal:
    return _require_capability(principal, "documents:write")


def require_document_review(
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> AuthPrincipal:
    return _require_capability(principal, "documents:review")


def require_admin(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> AuthPrincipal:
    return _require_capability(principal, "service:admin")


def require_jobs_admin(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> AuthPrincipal:
    return _require_capability(principal, "jobs:admin")


def require_parse_admin(
    principal: Annotated[AuthPrincipal, Depends(require_admin)],
) -> AuthPrincipal:
    return _require_capability(principal, "documents:read")


def require_admin_csrf(
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> AuthPrincipal:
    return _require_capability(principal, "jobs:admin")
