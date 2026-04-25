from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.low_level import Type
from pydantic import EmailStr

from lib.config import get_settings
from lib.contracts import SessionInfo
from lib.db.connection import db_connection

PASSWORD_HASHER = PasswordHasher(type=Type.ID)


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


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in slug.split("-") if part) or "structura"


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except VerifyMismatchError:
        return False


class AuthService:
    def bootstrap_admin(
        self,
        *,
        email: EmailStr,
        password: str,
        display_name: str = "Structura Admin",
        household_name: str = "Structura Household",
        must_rotate: bool = True,
    ) -> BootstrapResult:
        if len(password) < 8:
            raise AuthError("Bootstrap password must be at least 8 characters.")

        password_hash = hash_password(password)
        household_slug = slugify(household_name)
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO households (name, slug)
                    VALUES (%s, %s)
                    ON CONFLICT (slug) DO UPDATE
                    SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    (household_name, household_slug),
                )
                household = cur.fetchone()
                if not household:
                    raise AuthError("Failed to create household.")
                household_id = household["id"]
                cur.execute(
                    """
                    INSERT INTO users (email, display_name)
                    VALUES (%s, %s)
                    ON CONFLICT (email) DO UPDATE
                    SET display_name = EXCLUDED.display_name,
                        is_disabled = false
                    RETURNING id, email
                    """,
                    (str(email), display_name),
                )
                user = cur.fetchone()
                if not user:
                    raise AuthError("Failed to create user.")
                user_id = user["id"]
                cur.execute(
                    """
                    INSERT INTO household_memberships (household_id, user_id, role)
                    VALUES (%s, %s, 'owner')
                    ON CONFLICT (household_id, user_id) DO UPDATE
                    SET role = 'owner'
                    """,
                    (household_id, user_id),
                )
                cur.execute(
                    """
                    INSERT INTO user_password_credentials
                      (
                        user_id,
                        password_hash,
                        hash_algorithm,
                        params_json,
                        must_rotate,
                        disabled_at
                      )
                    VALUES (%s, %s, 'argon2id', '{}'::jsonb, %s, NULL)
                    ON CONFLICT (user_id) DO UPDATE
                    SET password_hash = EXCLUDED.password_hash,
                        hash_algorithm = 'argon2id',
                        params_json = '{}'::jsonb,
                        must_rotate = EXCLUDED.must_rotate,
                        disabled_at = NULL
                    """,
                    (user_id, password_hash, must_rotate),
                )
            conn.commit()
        return BootstrapResult(household_id=household_id, user_id=user_id, email=str(user["email"]))

    def create_password_session(
        self,
        *,
        email: str,
        password: str,
        household_id: UUID | None = None,
        user_agent: str | None = None,
        ip_hint: str | None = None,
    ) -> CreatedSession:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      u.id AS user_id,
                      u.email,
                      u.display_name,
                      c.password_hash,
                      c.must_rotate,
                      hm.household_id,
                      hm.role AS household_role
                    FROM users u
                    JOIN user_password_credentials c ON c.user_id = u.id
                    LEFT JOIN LATERAL (
                      SELECT household_id, role
                      FROM household_memberships
                      WHERE user_id = u.id
                        AND (%s::uuid IS NULL OR household_id = %s::uuid)
                      ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END
                      LIMIT 1
                    ) hm ON true
                    WHERE u.email = %s
                      AND u.is_disabled = false
                      AND c.disabled_at IS NULL
                    """,
                    (household_id, household_id, email),
                )
                user = cur.fetchone()
                if not user or not verify_password(user["password_hash"], password):
                    raise AuthError("Authentication failed.")
                if household_id and not user["household_id"]:
                    raise AuthError("User is not a member of that household.")
                cur.execute(
                    "UPDATE user_password_credentials SET last_used_at = now() WHERE user_id = %s",
                    (user["user_id"],),
                )
                session = self._insert_session(
                    cur,
                    user=user,
                    auth_method="password",
                    user_agent=user_agent,
                    ip_hint=ip_hint,
                )
            conn.commit()
        return session

    def request_magic_link(
        self,
        *,
        email: str,
        purpose: str,
        household_id: UUID | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.magic_link_ttl_minutes)
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT u.id AS user_id, hm.household_id
                    FROM users u
                    LEFT JOIN LATERAL (
                      SELECT household_id
                      FROM household_memberships
                      WHERE user_id = u.id
                        AND (%s::uuid IS NULL OR household_id = %s::uuid)
                      LIMIT 1
                    ) hm ON true
                    WHERE u.email = %s
                      AND u.is_disabled = false
                    """,
                    (household_id, household_id, email),
                )
                user = cur.fetchone()
                if user:
                    cur.execute(
                        """
                        INSERT INTO magic_links
                          (user_id, household_id, purpose, token_hash, expires_at)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            user["user_id"],
                            household_id or user["household_id"],
                            purpose,
                            hash_secret(token),
                            expires_at,
                        ),
                    )
            conn.commit()
        response: dict[str, Any] = {"accepted": True}
        if settings.environment != "production" and user:
            response["token"] = token
            response["expiresAt"] = expires_at.isoformat()
        return response

    def create_magic_link_session(
        self,
        *,
        token: str,
        household_id: UUID | None = None,
        user_agent: str | None = None,
        ip_hint: str | None = None,
    ) -> CreatedSession:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      ml.id AS magic_link_id,
                      u.id AS user_id,
                      u.email,
                      u.display_name,
                      ml.household_id,
                      hm.role AS household_role,
                      false AS must_rotate
                    FROM magic_links ml
                    JOIN users u ON u.id = ml.user_id
                    LEFT JOIN household_memberships hm
                      ON hm.user_id = u.id
                     AND hm.household_id = ml.household_id
                    WHERE ml.token_hash = %s
                      AND ml.used_at IS NULL
                      AND ml.expires_at > now()
                      AND u.is_disabled = false
                      AND (%s::uuid IS NULL OR ml.household_id = %s::uuid)
                    """,
                    (hash_secret(token), household_id, household_id),
                )
                user = cur.fetchone()
                if not user:
                    raise AuthError("Authentication failed.")
                cur.execute(
                    "UPDATE magic_links SET used_at = now() WHERE id = %s",
                    (user["magic_link_id"],),
                )
                session = self._insert_session(
                    cur,
                    user=user,
                    auth_method="magic_link",
                    user_agent=user_agent,
                    ip_hint=ip_hint,
                )
            conn.commit()
        return session

    def resolve_session_token(self, token: str) -> AuthPrincipal | None:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      s.id AS session_id,
                      s.user_id,
                      s.household_id,
                      s.auth_method::text AS auth_method,
                      u.email,
                      u.display_name,
                      hm.role AS household_role
                    FROM sessions s
                    JOIN users u ON u.id = s.user_id
                    LEFT JOIN household_memberships hm
                      ON hm.user_id = s.user_id
                     AND hm.household_id = s.household_id
                    WHERE s.token_hash = %s
                      AND s.revoked_at IS NULL
                      AND s.expires_at > now()
                      AND u.is_disabled = false
                    """,
                    (hash_secret(token),),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cur.execute(
                    "UPDATE sessions SET last_used_at = now() WHERE id = %s",
                    (row["session_id"],),
                )
            conn.commit()
        return AuthPrincipal(
            user_id=row["user_id"],
            household_id=row["household_id"],
            email=str(row["email"]),
            display_name=row["display_name"],
            auth_method=row["auth_method"],
            household_role=row.get("household_role"),
            session_id=row["session_id"],
        )

    def resolve_api_token(self, token: str) -> AuthPrincipal | None:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      t.id AS api_token_id,
                      t.user_id,
                      t.household_id,
                      t.scopes,
                      u.email,
                      u.display_name,
                      hm.role AS household_role
                    FROM api_tokens t
                    JOIN users u ON u.id = t.user_id
                    LEFT JOIN household_memberships hm
                      ON hm.user_id = t.user_id
                     AND hm.household_id = t.household_id
                    WHERE t.token_hash = %s
                      AND t.revoked_at IS NULL
                      AND (t.expires_at IS NULL OR t.expires_at > now())
                      AND u.is_disabled = false
                    """,
                    (hash_secret(token),),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cur.execute(
                    "UPDATE api_tokens SET last_used_at = now() WHERE id = %s",
                    (row["api_token_id"],),
                )
            conn.commit()
        return AuthPrincipal(
            user_id=row["user_id"],
            household_id=row["household_id"],
            email=str(row["email"]),
            display_name=row["display_name"],
            auth_method="api_token",
            household_role=row.get("household_role"),
            api_token_id=row["api_token_id"],
            scopes=tuple(row["scopes"] or ()),
        )

    def get_session_info(self, token: str) -> SessionInfo | None:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      s.id AS session_id,
                      s.user_id,
                      s.household_id,
                      s.auth_method::text AS auth_method,
                      s.expires_at,
                      u.email,
                      u.display_name,
                      COALESCE(c.must_rotate, false) AS password_rotation_required
                    FROM sessions s
                    JOIN users u ON u.id = s.user_id
                    LEFT JOIN user_password_credentials c ON c.user_id = u.id
                    WHERE s.token_hash = %s
                      AND s.revoked_at IS NULL
                      AND s.expires_at > now()
                      AND u.is_disabled = false
                    """,
                    (hash_secret(token),),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cur.execute(
                    "UPDATE sessions SET last_used_at = now() WHERE id = %s",
                    (row["session_id"],),
                )
            conn.commit()
        return self._session_info_from_row(row)

    def revoke_session(self, token: str) -> bool:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sessions
                    SET revoked_at = now()
                    WHERE token_hash = %s
                      AND revoked_at IS NULL
                    """,
                    (hash_secret(token),),
                )
                revoked = cur.rowcount > 0
            conn.commit()
        return revoked

    def _insert_session(
        self,
        cur: Any,
        *,
        user: dict[str, Any],
        auth_method: str,
        user_agent: str | None,
        ip_hint: str | None,
    ) -> CreatedSession:
        settings = get_settings()
        token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.session_ttl_minutes)
        cur.execute(
            """
            INSERT INTO sessions
              (user_id, household_id, auth_method, token_hash, user_agent, ip_hint, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s::inet, %s)
            RETURNING
              id AS session_id,
              user_id,
              household_id,
              auth_method::text AS auth_method,
              expires_at
            """,
            (
                user["user_id"],
                user["household_id"],
                auth_method,
                hash_secret(token),
                user_agent,
                ip_hint,
                expires_at,
            ),
        )
        row = cur.fetchone()
        row.update(
            {
                "email": user["email"],
                "display_name": user["display_name"],
                "password_rotation_required": bool(user.get("must_rotate", False)),
            }
        )
        return CreatedSession(
            token=token,
            csrf_token=csrf_token,
            session=self._session_info_from_row(row),
        )

    def _session_info_from_row(self, row: dict[str, Any]) -> SessionInfo:
        return SessionInfo.model_validate(
            {
                "sessionId": row["session_id"],
                "userId": row["user_id"],
                "householdId": row["household_id"],
                "displayName": row["display_name"],
                "email": row["email"],
                "authMethod": row["auth_method"],
                "isAuthenticated": True,
                "expiresAt": row["expires_at"],
                "passwordRotationRequired": row["password_rotation_required"],
            }
        )
