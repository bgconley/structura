from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from lib.auth import credential_repository


def issue_magic_link(
    cur: Any,
    *,
    email: str,
    household_id: UUID | None,
    purpose: str,
    token_hash: str,
    expires_at: datetime,
) -> bool:
    user = credential_repository.lock_user_by_email(cur, email)
    if user is None:
        return False
    cur.execute(
        """INSERT INTO magic_links (user_id, household_id, purpose, token_hash, expires_at)
        SELECT u.id, hm.household_id, %s, %s, %s FROM users u
        JOIN household_memberships hm ON hm.user_id = u.id
        WHERE u.id = %s AND NOT u.is_disabled
          AND (%s::uuid IS NULL OR hm.household_id = %s)
        ORDER BY hm.household_id LIMIT 1 RETURNING id""",
        (purpose, token_hash, expires_at, user["id"], household_id, household_id),
    )
    return cur.fetchone() is not None


def consume_magic_link(
    cur: Any, *, token_hash: str, household_id: UUID | None
) -> dict[str, Any] | None:
    cur.execute("SELECT user_id FROM magic_links WHERE token_hash = %s", (token_hash,))
    link = cur.fetchone()
    if link is None or link["user_id"] is None:
        return None
    if not credential_repository.lock_user(cur, link["user_id"]):
        return None
    # Conditional consumption and session creation share the caller's transaction.
    # The user lock serializes redemption with reset; the predicate is evaluated
    # anew after a concurrent redemption/reset, so precisely one request wins.
    cur.execute(
        """UPDATE magic_links ml SET used_at = clock_timestamp()
        FROM users u JOIN household_memberships hm ON hm.user_id = u.id
        LEFT JOIN user_password_credentials c ON c.user_id = u.id
        WHERE ml.token_hash = %s AND ml.user_id = u.id
          AND hm.household_id = ml.household_id AND NOT u.is_disabled
          AND ml.used_at IS NULL AND ml.expires_at > clock_timestamp()
          AND (%s::uuid IS NULL OR ml.household_id = %s)
        RETURNING u.id AS user_id, u.email, u.display_name, ml.household_id,
                  hm.role AS household_role, COALESCE(c.must_rotate, false) AS must_rotate""",
        (token_hash, household_id, household_id),
    )
    return cast(dict[str, Any] | None, cur.fetchone())
