"""Password identity persistence and serialized operator credential replacement.

Credential issuance/reset locks the user first, then reads current credentials
and membership. Session/token resolution never waits for a user lock while
holding a credential row, so reset cannot invert this order.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from lib.auth.models import AuthError


def bootstrap_admin(
    cur: Any,
    *,
    email: str,
    display_name: str,
    household_name: str,
    household_slug: str,
    password_hash: str,
    must_rotate: bool,
) -> dict[str, Any]:
    cur.execute(
        """INSERT INTO households (name, slug) VALUES (%s, %s)
        ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id""",
        (household_name, household_slug),
    )
    household = cur.fetchone()
    if household is None:
        raise AuthError("Failed to create household.")
    cur.execute(
        """INSERT INTO users (email, display_name) VALUES (%s, %s)
        ON CONFLICT (email) DO UPDATE
        SET display_name = EXCLUDED.display_name, is_disabled = false RETURNING id, email""",
        (email, display_name),
    )
    user = cur.fetchone()
    if user is None:
        raise AuthError("Failed to create user.")
    cur.execute(
        """INSERT INTO household_memberships (household_id, user_id, role)
        VALUES (%s, %s, 'owner') ON CONFLICT (household_id, user_id)
        DO UPDATE SET role = 'owner'""",
        (household["id"], user["id"]),
    )
    cur.execute(
        """INSERT INTO user_password_credentials
          (user_id, password_hash, hash_algorithm, params_json, must_rotate, disabled_at)
        VALUES (%s, %s, 'argon2id', '{}'::jsonb, %s, NULL)
        ON CONFLICT (user_id) DO UPDATE SET password_hash = EXCLUDED.password_hash,
          hash_algorithm = 'argon2id', params_json = '{}'::jsonb,
          must_rotate = EXCLUDED.must_rotate, disabled_at = NULL""",
        (user["id"], password_hash, must_rotate),
    )
    revoke_user_credentials(cur, user["id"])
    return {"household_id": household["id"], "user_id": user["id"], "email": str(user["email"])}


def revoke_user_credentials(cur: Any, user_id: UUID) -> None:
    """The caller holds the user lock; reset and credential issuance are atomic."""
    cur.execute(
        "UPDATE sessions SET revoked_at = clock_timestamp() "
        "WHERE user_id = %s AND revoked_at IS NULL",
        (user_id,),
    )
    cur.execute(
        "UPDATE api_tokens SET revoked_at = clock_timestamp() "
        "WHERE user_id = %s AND revoked_at IS NULL",
        (user_id,),
    )
    cur.execute(
        "UPDATE magic_links SET used_at = clock_timestamp() WHERE user_id = %s AND used_at IS NULL",
        (user_id,),
    )


def lock_user_by_email(cur: Any, email: str) -> dict[str, Any] | None:
    cur.execute("SELECT id FROM users WHERE email = %s FOR UPDATE", (email,))
    return cast(dict[str, Any] | None, cur.fetchone())


def lock_user(cur: Any, user_id: UUID) -> bool:
    cur.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
    return cur.fetchone() is not None


def password_identity(cur: Any, user_id: UUID, household_id: UUID | None) -> dict[str, Any] | None:
    # A new statement after the user lock sees a reset/downgrade that committed
    # while this login waited. No membership means no issuable session.
    cur.execute(
        """SELECT u.id AS user_id, u.email, u.display_name, c.password_hash,
                  c.must_rotate, hm.household_id, hm.role AS household_role
        FROM users u JOIN user_password_credentials c ON c.user_id = u.id
        JOIN household_memberships hm ON hm.user_id = u.id
        WHERE u.id = %s AND NOT u.is_disabled AND c.disabled_at IS NULL
          AND (%s::uuid IS NULL OR hm.household_id = %s)
        ORDER BY CASE hm.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
                 hm.household_id LIMIT 1""",
        (user_id, household_id, household_id),
    )
    return cast(dict[str, Any] | None, cur.fetchone())


def touch_password(cur: Any, user_id: UUID) -> None:
    cur.execute(
        "UPDATE user_password_credentials SET last_used_at = clock_timestamp() WHERE user_id = %s",
        (user_id,),
    )
