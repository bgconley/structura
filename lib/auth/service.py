from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import EmailStr

from lib.auth import (
    credential_repository,
    magic_link_repository,
    session_repository,
    token_repository,
)
from lib.auth.models import AuthError as AuthError
from lib.auth.models import AuthPrincipal as AuthPrincipal
from lib.auth.models import BootstrapResult as BootstrapResult
from lib.auth.models import CreatedSession as CreatedSession
from lib.auth.primitives import hash_password as hash_password
from lib.auth.primitives import hash_secret as hash_secret
from lib.auth.primitives import slugify as slugify
from lib.auth.primitives import verify_password as verify_password
from lib.config import get_settings
from lib.contracts import SessionInfo
from lib.db.connection import db_connection


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
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = credential_repository.bootstrap_admin(
                    cur,
                    email=str(email),
                    display_name=display_name,
                    household_name=household_name,
                    household_slug=slugify(household_name),
                    password_hash=password_hash,
                    must_rotate=must_rotate,
                )
            conn.commit()
        return BootstrapResult(**row)

    def create_password_session(
        self,
        *,
        email: str,
        password: str,
        household_id: UUID | None = None,
        user_agent: str | None = None,
        ip_hint: str | None = None,
        replaces_session: AuthPrincipal | None = None,
    ) -> CreatedSession:
        with db_connection() as conn:
            with conn.cursor() as cur:
                identity = credential_repository.lock_user_by_email(cur, email)
                user = (
                    credential_repository.password_identity(cur, identity["id"], household_id)
                    if identity
                    else None
                )
                if not user or not verify_password(user["password_hash"], password):
                    raise AuthError("Authentication failed.")
                credential_repository.touch_password(cur, user["user_id"])
                session = self._insert_session(
                    cur,
                    user=user,
                    auth_method="password",
                    user_agent=user_agent,
                    ip_hint=ip_hint,
                    replaces_session=replaces_session,
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
        if purpose not in {"bootstrap", "invite", "recovery"}:
            raise AuthError("Unsupported magic-link purpose.")
        settings = get_settings()
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.magic_link_ttl_minutes)
        with db_connection() as conn:
            with conn.cursor() as cur:
                issued = magic_link_repository.issue_magic_link(
                    cur,
                    email=email,
                    household_id=household_id,
                    purpose=purpose,
                    token_hash=hash_secret(token),
                    expires_at=expires_at,
                )
            conn.commit()
        # Acknowledges the request, not delivery; no delivery adapter exists yet.
        response: dict[str, Any] = {"accepted": True}
        if (
            settings.environment == "test"
            and settings.return_magic_link_tokens_for_tests
            and issued
        ):
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
        replaces_session: AuthPrincipal | None = None,
    ) -> CreatedSession:
        with db_connection() as conn:
            with conn.cursor() as cur:
                user = magic_link_repository.consume_magic_link(
                    cur,
                    token_hash=hash_secret(token),
                    household_id=household_id,
                )
                if user is None:
                    raise AuthError("Authentication failed.")
                session = self._insert_session(
                    cur,
                    user=user,
                    auth_method="magic_link",
                    user_agent=user_agent,
                    ip_hint=ip_hint,
                    replaces_session=replaces_session,
                )
            conn.commit()
        return session

    def resolve_session_token(self, token: str) -> AuthPrincipal | None:
        row = self._active_session(token)
        if row is None:
            return None
        return AuthPrincipal(
            user_id=row["user_id"],
            household_id=row["household_id"],
            email=str(row["email"]),
            display_name=row["display_name"],
            auth_method=row["auth_method"],
            household_role=row["household_role"],
            session_id=row["session_id"],
            csrf_token_hash=row["csrf_token_hash"],
        )

    def resolve_api_token(self, token: str) -> AuthPrincipal | None:
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = token_repository.active_api_token(cur, hash_secret(token))
            conn.commit()
        if row is None:
            return None
        return AuthPrincipal(
            user_id=row["user_id"],
            household_id=row["household_id"],
            email=str(row["email"]),
            display_name=row["display_name"],
            auth_method="api_token",
            household_role=row["household_role"],
            api_token_id=row["api_token_id"],
            scopes=tuple(row["scopes"] or ()),
        )

    def get_session_info(self, token: str) -> SessionInfo | None:
        row = self._active_session(token)
        return self._session_info_from_row(row) if row is not None else None

    def _active_session(self, token: str) -> dict[str, Any] | None:
        with db_connection() as conn:
            with conn.cursor() as cur:
                row = session_repository.active_session(cur, hash_secret(token))
            conn.commit()
        return row

    def revoke_session(self, token: str) -> bool:
        with db_connection() as conn:
            with conn.cursor() as cur:
                revoked = session_repository.revoke_session(cur, hash_secret(token))
            conn.commit()
        return revoked

    def revoke_authenticated_session(self, principal: AuthPrincipal) -> bool:
        if principal.session_id is None or principal.api_token_id is not None:
            raise AuthError("Browser session required.")
        with db_connection() as conn:
            with conn.cursor() as cur:
                revoked = session_repository.revoke_authenticated_session(
                    cur,
                    principal.session_id,
                    principal.user_id,
                )
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
        replaces_session: AuthPrincipal | None = None,
    ) -> CreatedSession:
        settings = get_settings()
        token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        if replaces_session is not None:
            if (
                replaces_session.session_id is None
                or not session_repository.consume_session_replacement(
                    cur,
                    replaces_session.session_id,
                    replaces_session.user_id,
                )
            ):
                raise AuthError("Authentication failed.")
        row = session_repository.insert_session(
            cur,
            user_id=user["user_id"],
            household_id=user["household_id"],
            auth_method=auth_method,
            token_hash=hash_secret(token),
            csrf_token_hash=hash_secret(csrf_token),
            user_agent=user_agent,
            ip_hint=ip_hint,
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.session_ttl_minutes),
        )
        row.update(
            email=user["email"],
            display_name=user["display_name"],
            password_rotation_required=bool(user.get("must_rotate", False)),
        )
        return CreatedSession(token, csrf_token, self._session_info_from_row(row))

    def _session_info_from_row(self, row: dict[str, Any]) -> SessionInfo:
        settings = get_settings()
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
                "sessionCookieName": settings.session_cookie_name,
                "csrfCookieName": settings.csrf_cookie_name,
            }
        )
