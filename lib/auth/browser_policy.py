"""Session-bound browser request checks, independent of the HTTP framework."""

from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from lib.auth.primitives import hash_secret


class BrowserSecurityError(Exception):
    pass


def require_browser_origin(
    *, origin: str | None, has_fetch_metadata: bool, expected_origin: str
) -> None:
    if origin is None:
        # Non-browser CLI/test clients may omit these browser-controlled headers.
        # Cookie-authenticated mutations still require their bound CSRF secret.
        if not has_fetch_metadata:
            return
        raise BrowserSecurityError("Request origin not allowed")
    if _origin_identity(origin) != _origin_identity(expected_origin):
        raise BrowserSecurityError("Request origin not allowed")


def _origin_identity(value: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or value != value.strip()
            or "," in value
        ):
            raise ValueError
        if parsed.port is not None and parsed.port < 1:
            raise ValueError
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        return parsed.scheme, parsed.hostname, port
    except ValueError:
        raise BrowserSecurityError("Request origin not allowed") from None


def require_session_csrf(
    *, cookie: str | None, header: str | None, session_csrf_hash: str | None
) -> None:
    if (
        not cookie
        or not header
        or not session_csrf_hash
        or not secrets.compare_digest(cookie.encode(), header.encode())
        or not secrets.compare_digest(hash_secret(header), session_csrf_hash)
    ):
        raise BrowserSecurityError("CSRF token required")
