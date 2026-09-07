from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue
from typing import LiteralString, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation, InvalidTextRepresentation
from psycopg.sql import SQL

from apps.api.structura_api.main import create_app
from lib.auth import AuthError, AuthService, credential_repository, hash_secret
from lib.auth.primitives import hash_password, slugify
from lib.config import get_settings
from lib.db.connection import db_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"), reason="Isolated test database required"
)
ORIGIN = "http://localhost:3000"
PASSWORD = "minimum8"
NEW_PASSWORD = "changed-minimum8"


def sql(statement, params=()):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall() if cur.description else []


@pytest.fixture
def account(monkeypatch, tmp_path):
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    monkeypatch.setenv("STRUCTURA_WEB_ORIGIN", ORIGIN)
    monkeypatch.setenv("STRUCTURA_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("STRUCTURA_RETURN_MAGIC_LINK_TOKENS_FOR_TESTS", "false")
    get_settings.cache_clear()
    unique = uuid4().hex
    household_name = f"Session {unique}"
    owner = AuthService().bootstrap_admin(
        email=f"session-{unique}@example.com", password=PASSWORD, household_name=household_name
    )
    yield owner, household_name
    get_settings.cache_clear()


def client_for(owner):
    client = TestClient(create_app(), headers={"Origin": ORIGIN})
    result = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": owner.email, "password": PASSWORD},
    )
    assert result.status_code == 201, result.text
    return client


def cookie_pair(client):
    return client.cookies["structura_session"], client.cookies["structura_csrf"]


def write_tag(client, *, headers=None):
    return client.post("/api/v1/tags", json={"name": uuid4().hex}, headers=headers)


def token_for(owner, scopes):
    token = uuid4().hex
    sql(
        "INSERT INTO api_tokens (user_id,household_id,label,token_hash,scopes) "
        "VALUES (%s,%s,%s,%s,%s)",
        (owner.user_id, owner.household_id, "Session test", hash_secret(token), scopes),
    )
    return token


def magic_for(owner):
    token = uuid4().hex
    sql(
        """INSERT INTO magic_links (user_id,household_id,purpose,token_hash,expires_at)
        VALUES (%s,%s,'recovery',%s,clock_timestamp() + interval '10 minutes')""",
        (owner.user_id, owner.household_id, hash_secret(token)),
    )
    return token


def test_csrf_binding_and_origin_protect_real_mutations(account):
    owner, _ = account
    client = client_for(owner)
    session, csrf = cookie_pair(client)
    other = client_for(owner)
    _, other_csrf = cookie_pair(other)
    before = sql("SELECT count(*) AS n FROM tags WHERE household_id=%s", (owner.household_id,))
    for candidate in (None, "arbitrary", other_csrf):
        headers = {"Cookie": f"structura_session={session}; structura_csrf={candidate or csrf}"}
        if candidate:
            headers["X-CSRF-Token"] = candidate
        assert write_tag(client, headers=headers).status_code == 403
    for origin in ("https://foreign.example", "null"):
        assert (
            write_tag(client, headers={"Origin": origin, "X-CSRF-Token": csrf}).status_code == 403
        )
    client.headers.pop("Origin")
    assert (
        write_tag(
            client, headers={"Sec-Fetch-Site": "same-origin", "X-CSRF-Token": csrf}
        ).status_code
        == 403
    )
    assert (
        sql("SELECT count(*) AS n FROM tags WHERE household_id=%s", (owner.household_id,)) == before
    )
    # Non-browser compatibility still requires the correct session-bound secret.
    assert write_tag(client, headers={"X-CSRF-Token": csrf}).status_code == 201
    client.headers["Origin"] = ORIGIN
    assert write_tag(client, headers={"X-CSRF-Token": csrf}).status_code == 201
    assert sql(
        "SELECT csrf_token_hash FROM sessions WHERE token_hash=%s", (hash_secret(session),)
    ) == [{"csrf_token_hash": hash_secret(csrf)}]


def test_token_auth_cannot_authorize_cookie_logout_or_bypass_its_scope(account):
    owner, _ = account
    client = client_for(owner)
    session, csrf = cookie_pair(client)
    token = token_for(owner, ["documents:write"])
    assert write_tag(client, headers={"X-API-Token": token}).status_code == 201
    assert client.delete("/api/v1/auth/session", headers={"X-API-Token": token}).status_code == 403
    assert AuthService().resolve_session_token(session) is not None
    assert (
        write_tag(client, headers={"X-API-Token": "invalid", "X-CSRF-Token": csrf}).status_code
        == 401
    )
    read_token = token_for(owner, ["documents:read"])
    assert write_tag(client, headers={"X-API-Token": read_token}).status_code == 403
    assert client.delete("/api/v1/auth/session", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert not client.cookies.get("structura_session") and not client.cookies.get("structura_csrf")
    assert AuthService().resolve_session_token(session) is None
    assert AuthService().resolve_api_token(token) is not None


def test_login_replacement_requires_csrf_and_revokes_only_after_success(account):
    owner, _ = account
    client = client_for(owner)
    old_session, old_csrf = cookie_pair(client)
    login = {"method": "password", "email": owner.email, "password": PASSWORD}
    assert client.post("/api/v1/auth/session", json=login).status_code == 403
    bad_password = {**login, "password": "incorrect8"}
    assert (
        client.post(
            "/api/v1/auth/session", json=bad_password, headers={"X-CSRF-Token": old_csrf}
        ).status_code
        == 401
    )
    assert AuthService().resolve_session_token(old_session) is not None
    replaced = client.post("/api/v1/auth/session", json=login, headers={"X-CSRF-Token": old_csrf})
    assert replaced.status_code == 201, replaced.text
    assert cookie_pair(client) != (old_session, old_csrf)
    assert AuthService().resolve_session_token(old_session) is None
    assert write_tag(client, headers={"X-CSRF-Token": old_csrf}).status_code == 403


def test_login_recovery_origins_and_absent_membership_fail_closed(account):
    owner, _ = account
    client = TestClient(create_app())
    login = {"method": "password", "email": owner.email, "password": PASSWORD}
    for headers in (
        {"Origin": "null"},
        {"Origin": "https://foreign.example"},
        {"Sec-Fetch-Mode": "cors"},
    ):
        assert client.post("/api/v1/auth/session", json=login, headers=headers).status_code == 403
        assert (
            client.post(
                "/api/v1/auth/magic-links",
                json={"email": owner.email, "purpose": "recovery"},
                headers=headers,
            ).status_code
            == 403
        )
    sql("DELETE FROM household_memberships WHERE user_id=%s", (owner.user_id,))
    assert client.post("/api/v1/auth/session", json=login).status_code == 401
    for email in (owner.email, f"unknown-{uuid4().hex}@example.com"):
        response = client.post(
            "/api/v1/auth/magic-links", json={"email": email, "purpose": "recovery"}
        )
        assert response.status_code == 202 and response.json() == {"accepted": True}
    assert sql("SELECT id FROM sessions WHERE user_id=%s", (owner.user_id,)) == []
    assert sql("SELECT id FROM magic_links WHERE user_id=%s", (owner.user_id,)) == []


def test_credential_reset_revokes_sessions_tokens_and_unused_links(account):
    owner, household = account
    client = client_for(owner)
    session, _ = cookie_pair(client)
    token = token_for(owner, ["documents:write"])
    magic = magic_for(owner)
    AuthService().bootstrap_admin(
        email=owner.email, password=NEW_PASSWORD, household_name=household
    )
    assert AuthService().resolve_session_token(session) is None
    assert AuthService().get_session_info(session) is None
    assert AuthService().resolve_api_token(token) is None
    with pytest.raises(AuthError):
        AuthService().create_magic_link_session(token=magic)
    with pytest.raises(AuthError):
        AuthService().create_password_session(email=owner.email, password=PASSWORD)
    assert (
        AuthService()
        .create_password_session(email=owner.email, password=NEW_PASSWORD)
        .session.user_id
        == owner.user_id
    )


def test_absolute_expiry_blocks_read_and_write_with_matching_csrf(account):
    owner, _ = account
    client = client_for(owner)
    session, csrf = cookie_pair(client)
    sql(
        "UPDATE sessions SET expires_at=clock_timestamp() - interval '1 second' "
        "WHERE token_hash=%s",
        (hash_secret(session),),
    )
    assert client.get("/api/v1/auth/session").status_code == 401
    assert write_tag(client, headers={"X-CSRF-Token": csrf}).status_code == 401


def test_magic_link_consumption_rolls_back_if_session_insert_fails(account):
    owner, _ = account
    token = magic_for(owner)
    with pytest.raises(InvalidTextRepresentation):
        AuthService().create_magic_link_session(token=token, ip_hint="invalid-synthetic-ip")
    assert sql("SELECT used_at FROM magic_links WHERE token_hash=%s", (hash_secret(token),)) == [
        {"used_at": None}
    ]
    assert sql("SELECT id FROM sessions WHERE user_id=%s", (owner.user_id,)) == []
    assert AuthService().create_magic_link_session(token=token).session.user_id == owner.user_id


def observe_user_locks(monkeypatch):
    backends = Queue()
    for name in ("lock_user", "lock_user_by_email"):
        original = getattr(credential_repository, name)

        def wrapped(cur, value, _original=original):
            backends.put(cur.connection.info.backend_pid)
            return _original(cur, value)

        monkeypatch.setattr(credential_repository, name, wrapped)
    return backends


def wait_for_blocked(cur, blocker, waiter):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        cur.execute("SELECT %s = ANY(pg_blocking_pids(%s)) AS blocked", (blocker, waiter))
        if cur.fetchone()["blocked"]:
            return
        time.sleep(0.01)
    pytest.fail("Concurrent auth request did not reach the expected lock")


def test_concurrent_magic_link_redemption_creates_exactly_one_session(account, monkeypatch):
    owner, _ = account
    token = magic_for(owner)
    backends = observe_user_locks(monkeypatch)

    def redeem():
        try:
            return AuthService().create_magic_link_session(token=token).session.session_id
        except AuthError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        with db_connection() as blocker, blocker.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id=%s FOR UPDATE", (owner.user_id,))
            futures = [pool.submit(redeem) for _ in range(2)]
            try:
                for _ in futures:
                    wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
        results = [future.result(timeout=10) for future in futures]
    assert sum(result is not None for result in results) == 1
    assert len(sql("SELECT id FROM sessions WHERE user_id=%s", (owner.user_id,))) == 1
    assert (
        sql("SELECT used_at FROM magic_links WHERE token_hash=%s", (hash_secret(token),))[0][
            "used_at"
        ]
        is not None
    )


@pytest.mark.parametrize("method", ["password", "magic_link"])
def test_login_waiting_for_reset_rechecks_new_credentials(account, monkeypatch, method):
    owner, household = account
    magic = magic_for(owner)
    backends = observe_user_locks(monkeypatch)

    def login():
        if method == "password":
            return AuthService().create_password_session(email=owner.email, password=PASSWORD)
        return AuthService().create_magic_link_session(token=magic)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_connection() as blocker, blocker.cursor() as cur:
            credential_repository.bootstrap_admin(
                cur,
                email=owner.email,
                display_name="Reset owner",
                household_name=household,
                household_slug=slugify(household),
                password_hash=hash_password(NEW_PASSWORD),
                must_rotate=True,
            )
            future = pool.submit(login)
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
        with pytest.raises(AuthError):
            future.result(timeout=10)
    assert sql("SELECT id FROM sessions WHERE user_id=%s", (owner.user_id,)) == []


def test_reset_waits_for_issuance_then_revokes_the_new_session(account, monkeypatch):
    owner, household = account
    backends = Queue()
    original = credential_repository.bootstrap_admin

    def observed_reset(cur, **kwargs):
        backends.put(cur.connection.info.backend_pid)
        return original(cur, **kwargs)

    monkeypatch.setattr(credential_repository, "bootstrap_admin", observed_reset)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_connection() as issuer, issuer.cursor() as cur:
            credential_repository.lock_user_by_email(cur, owner.email)
            user = credential_repository.password_identity(cur, owner.user_id, owner.household_id)
            assert user is not None
            created = AuthService()._insert_session(
                cur, user=user, auth_method="password", user_agent=None, ip_hint=None
            )
            reset = pool.submit(
                AuthService().bootstrap_admin,
                email=owner.email,
                password=NEW_PASSWORD,
                household_name=household,
            )
            try:
                wait_for_blocked(cur, issuer.info.backend_pid, backends.get(timeout=5))
            finally:
                issuer.commit()
        reset.result(timeout=10)
    assert AuthService().resolve_session_token(created.token) is None


def test_legacy_upgrade_revokes_unbound_sessions_and_prevents_new_unbound_rows(account):
    owner, _ = account
    client_for(owner)
    migration = (
        Path(__file__).resolve().parents[2] / "database/095_completion_session_binding.sql"
    ).read_text()
    with db_connection() as conn, conn.cursor() as cur:
        # Restore the pre-095 table shape inside a rolled-back transaction, then
        # run the actual upgrade against a live legacy session.
        cur.execute("ALTER TABLE sessions DROP CONSTRAINT sessions_bound_csrf_check")
        cur.execute("ALTER TABLE sessions DROP COLUMN csrf_token_hash")
        cur.execute(SQL(cast(LiteralString, migration)), prepare=False)
        cur.execute(
            "SELECT revoked_at,csrf_token_hash FROM sessions WHERE user_id=%s", (owner.user_id,)
        )
        rows = cur.fetchall()
        assert rows and all(
            row["revoked_at"] is not None and row["csrf_token_hash"] is None for row in rows
        )
        cur.execute("SAVEPOINT invalid_session")
        with pytest.raises(CheckViolation):
            cur.execute(
                """INSERT INTO sessions (user_id,household_id,auth_method,token_hash,expires_at)
                VALUES (%s,%s,'password',%s,clock_timestamp() + interval '1 hour')""",
                (owner.user_id, owner.household_id, hash_secret(uuid4().hex)),
            )
        cur.execute("ROLLBACK TO SAVEPOINT invalid_session")
        conn.rollback()
