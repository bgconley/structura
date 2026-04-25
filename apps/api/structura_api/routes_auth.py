from __future__ import annotations

import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from apps.api.structura_api.dependencies import require_csrf, session_cookie_value
from lib.auth import AuthError, AuthService
from lib.config import get_settings
from lib.contracts import (
    CreateMagicLinkRequest,
    CreateSessionRequest,
    MagicLinkSessionRequest,
    PasswordSessionRequest,
    SessionInfo,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


def request_ip_hint(request: Request) -> str | None:
    if not request.client:
        return None
    host = request.client.host
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return host


def set_session_cookies(response: Response, *, token: str, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.get("/session", response_model=SessionInfo)
def get_session(request: Request) -> SessionInfo:
    structura_session = session_cookie_value(request)
    if not structura_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    session = AuthService().get_session_info(structura_session)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return session


@router.post("/session", response_model=SessionInfo, status_code=status.HTTP_201_CREATED)
def create_session(
    body: CreateSessionRequest,
    request: Request,
    response: Response,
) -> SessionInfo:
    service = AuthService()
    try:
        if isinstance(body, PasswordSessionRequest):
            created = service.create_password_session(
                email=str(body.email),
                password=body.password,
                household_id=body.household_id,
                user_agent=request.headers.get("user-agent"),
                ip_hint=request_ip_hint(request),
            )
        elif isinstance(body, MagicLinkSessionRequest):
            created = service.create_magic_link_session(
                token=body.magic_link_token,
                household_id=body.household_id,
                user_agent=request.headers.get("user-agent"),
                ip_hint=request_ip_hint(request),
            )
        else:  # pragma: no cover - Pydantic discriminator keeps this unreachable.
            raise AuthError("Unsupported session method.")
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    set_session_cookies(response, token=created.token, csrf_token=created.csrf_token)
    return created.session


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    request: Request,
    response: Response,
    _principal: Annotated[object, Depends(require_csrf)],
) -> Response:
    structura_session = session_cookie_value(request)
    if structura_session:
        AuthService().revoke_session(structura_session)
    clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/magic-links", status_code=status.HTTP_202_ACCEPTED)
def create_magic_link(
    payload: CreateMagicLinkRequest,
) -> dict[str, object]:
    return AuthService().request_magic_link(
        email=str(payload.email),
        purpose=payload.purpose,
        household_id=payload.household_id,
    )
