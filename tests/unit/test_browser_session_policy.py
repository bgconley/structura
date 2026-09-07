from __future__ import annotations

from http.cookies import SimpleCookie

import pytest
from fastapi import Response

from apps.api.structura_api.routes_auth import clear_session_cookies, set_session_cookies
from lib.auth.browser_policy import (
    BrowserSecurityError,
    require_browser_origin,
    require_session_csrf,
)
from lib.auth.primitives import hash_secret, verify_password
from lib.config import Settings, get_settings


@pytest.mark.parametrize("origin", ["https://app.example", "https://APP.example:443"])
def test_browser_origin_uses_exact_scheme_host_and_port(origin):
    require_browser_origin(
        origin=origin, has_fetch_metadata=True, expected_origin="https://app.example"
    )


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "https://other.example",
        "http://app.example",
        "https://app.example:444",
        "https://app.example.evil",
        "https://app.example/",
        "https://user@app.example",
        "https://app.example,https://other.example",
        " https://app.example",
    ],
)
def test_foreign_or_malformed_browser_origin_is_denied(origin):
    with pytest.raises(BrowserSecurityError):
        require_browser_origin(
            origin=origin, has_fetch_metadata=False, expected_origin="https://app.example"
        )


def test_missing_origin_compatibility_does_not_exempt_browser_requests():
    require_browser_origin(
        origin=None, has_fetch_metadata=False, expected_origin="http://localhost:3000"
    )
    with pytest.raises(BrowserSecurityError):
        require_browser_origin(
            origin=None, has_fetch_metadata=True, expected_origin="http://localhost:3000"
        )


@pytest.mark.parametrize("cookie,header", [(None, None), ("a", None), ("a", "b"), ("b", "b")])
def test_csrf_requires_the_secret_bound_to_this_session(cookie, header):
    with pytest.raises(BrowserSecurityError):
        require_session_csrf(cookie=cookie, header=header, session_csrf_hash=hash_secret("a"))


def test_matching_but_unbound_csrf_is_denied_and_bound_secret_works():
    with pytest.raises(BrowserSecurityError):
        require_session_csrf(cookie="a", header="a", session_csrf_hash=None)
    require_session_csrf(cookie="a", header="a", session_csrf_hash=hash_secret("a"))


def test_local_http_and_tls_cookie_profiles_are_explicit(monkeypatch):
    for secure, origin in ((False, "http://localhost:3000"), (True, "https://app.example")):
        monkeypatch.setenv("STRUCTURA_WEB_ORIGIN", origin)
        monkeypatch.setenv("STRUCTURA_SESSION_COOKIE_SECURE", str(secure).lower())
        get_settings.cache_clear()
        response = Response()
        set_session_cookies(response, token="synthetic-session", csrf_token="synthetic-csrf")
        cookies = SimpleCookie()
        for raw in response.headers.getlist("set-cookie"):
            cookies.load(raw)
        session = cookies["structura_session"]
        csrf = cookies["structura_csrf"]
        assert bool(session["secure"]) is secure and bool(csrf["secure"]) is secure
        assert session["httponly"] and not csrf["httponly"]
        assert session["samesite"] == csrf["samesite"] == "lax"
        assert session["path"] == csrf["path"] == "/"
        cleared = Response()
        clear_session_cookies(cleared)
        for raw in cleared.headers.getlist("set-cookie"):
            cookie = SimpleCookie(raw)
            value = next(iter(cookie.values()))
            assert value["max-age"] == "0" and bool(value["secure"]) is secure
    get_settings.cache_clear()


def test_unsafe_tls_and_unbounded_expiry_configuration_is_rejected():
    with pytest.raises(ValueError, match="Secure"):
        Settings.model_validate(
            {"web_origin": "https://app.example", "session_cookie_secure": False}
        )
    for field in ("session_ttl_minutes", "magic_link_ttl_minutes"):
        with pytest.raises(ValueError):
            Settings.model_validate({field: 0})


def test_invalid_persisted_password_hash_fails_authentication():
    assert not verify_password("corrupt-synthetic-hash", "minimum8")
