"""Isolated legacy upload actors and storage; actual auth/body/persistence remain wired."""

import os
from uuid import uuid4

import pytest
from starlette import formparsers

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.auth.request_authority import RequestCredential
from lib.config import get_settings

from .support import LegacyUpload


@pytest.fixture
def legacy_upload(monkeypatch, tmp_path):
    url = os.environ.get("STRUCTURA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires isolated PostgreSQL with committed request-authority helpers.")
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("STRUCTURA_WEB_ORIGIN", "http://testserver")
    monkeypatch.setenv("STRUCTURA_SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    identity = uuid4().hex
    auth = AuthService()
    owner = auth.bootstrap_admin(
        email=f"legacy-upload-{identity}@example.com",
        password="minimum8",
        household_name=f"Legacy upload {identity}",
        must_rotate=False,
    )
    session = auth.create_password_session(email=owner.email, password="minimum8")
    principal = auth.resolve_session_token(session.token)
    assert principal is not None
    spools = []
    original = formparsers.SpooledTemporaryFile

    def observe_spool(*args, **kwargs):
        spool = original(*args, **kwargs)
        spools.append(spool)
        return spool

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", observe_spool)
    yield LegacyUpload(
        create_app(),
        session,
        RequestCredential.from_principal(principal),
        owner.email,
        f"legacy-{identity}.pdf",
        f"%PDF-1.7\n% legacy credential {identity}\n%%EOF\n".encode(),
        get_settings().runtime_root,
        spools,
    )
    get_settings.cache_clear()
