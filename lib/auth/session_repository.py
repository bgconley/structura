"""Browser session persistence; active-state reads follow the row lock."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from lib.auth.models import AuthError


def insert_session(
    cur: Any,
    *,
    user_id: UUID,
    household_id: UUID,
    auth_method: str,
    token_hash: str,
    csrf_token_hash: str,
    user_agent: str | None,
    ip_hint: str | None,
    expires_at: datetime,
) -> dict[str, Any]:
    cur.execute(
        """INSERT INTO sessions
          (user_id, household_id, auth_method, token_hash, csrf_token_hash,
           user_agent, ip_hint, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s::inet, %s)
        RETURNING id AS session_id, user_id, household_id,
                  auth_method::text AS auth_method, expires_at""",
        (
            user_id,
            household_id,
            auth_method,
            token_hash,
            csrf_token_hash,
            user_agent,
            ip_hint,
            expires_at,
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise AuthError("Session was not created.")
    return cast(dict[str, Any], row)


def active_session(cur: Any, token_hash: str) -> dict[str, Any] | None:
    cur.execute("SELECT id FROM sessions WHERE token_hash = %s FOR UPDATE", (token_hash,))
    if cur.fetchone() is None:
        return None
    cur.execute(
        """SELECT s.id AS session_id, s.user_id, s.household_id,
                  s.auth_method::text AS auth_method, s.expires_at, s.csrf_token_hash,
                  u.email, u.display_name, hm.role AS household_role,
                  COALESCE(c.must_rotate, false) AS password_rotation_required
        FROM sessions s JOIN users u ON u.id = s.user_id
        JOIN household_memberships hm
          ON hm.user_id = s.user_id AND hm.household_id = s.household_id
        LEFT JOIN user_password_credentials c ON c.user_id = u.id
        WHERE s.token_hash = %s AND s.revoked_at IS NULL
          AND s.csrf_token_hash IS NOT NULL AND s.expires_at > clock_timestamp()
          AND NOT u.is_disabled""",
        (token_hash,),
    )
    row = cur.fetchone()
    if row is not None:
        cur.execute(
            "UPDATE sessions SET last_used_at = clock_timestamp() WHERE id = %s "
            "AND (last_used_at IS NULL OR last_used_at < clock_timestamp() - interval '1 minute')",
            (row["session_id"],),
        )
    return cast(dict[str, Any] | None, row)


def revoke_session(cur: Any, token_hash: str) -> bool:
    cur.execute(
        "UPDATE sessions SET revoked_at = clock_timestamp() "
        "WHERE token_hash = %s AND revoked_at IS NULL",
        (token_hash,),
    )
    return bool(cur.rowcount)


def revoke_authenticated_session(cur: Any, session_id: UUID, user_id: UUID) -> bool:
    cur.execute(
        "UPDATE sessions SET revoked_at = clock_timestamp() "
        "WHERE id = %s AND user_id = %s AND revoked_at IS NULL",
        (session_id, user_id),
    )
    return bool(cur.rowcount)


def consume_session_replacement(cur: Any, session_id: UUID, user_id: UUID) -> bool:
    cur.execute(
        "UPDATE sessions SET revoked_at = clock_timestamp() "
        "WHERE id = %s AND user_id = %s AND revoked_at IS NULL "
        "AND expires_at > clock_timestamp()",
        (session_id, user_id),
    )
    return bool(cur.rowcount)
