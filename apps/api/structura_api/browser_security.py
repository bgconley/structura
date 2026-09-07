from __future__ import annotations

from fastapi import HTTPException, Request

from lib.auth import AuthPrincipal
from lib.auth.browser_policy import (
    BrowserSecurityError,
    require_browser_origin,
    require_session_csrf,
)
from lib.config import get_settings


def validate_browser_origin(request: Request) -> None:
    try:
        require_browser_origin(
            origin=request.headers.get("origin"),
            has_fetch_metadata=any(name.startswith("sec-fetch-") for name in request.headers),
            expected_origin=get_settings().web_origin,
        )
    except BrowserSecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def validate_browser_session(request: Request, principal: AuthPrincipal, csrf: str | None) -> None:
    validate_browser_origin(request)
    try:
        require_session_csrf(
            cookie=request.cookies.get(get_settings().csrf_cookie_name),
            header=csrf,
            session_csrf_hash=principal.csrf_token_hash,
        )
    except BrowserSecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
