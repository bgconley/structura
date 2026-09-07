from __future__ import annotations

from typing import Any, cast


def active_api_token(cur: Any, token_hash: str) -> dict[str, Any] | None:
    cur.execute("SELECT id FROM api_tokens WHERE token_hash = %s FOR UPDATE", (token_hash,))
    if cur.fetchone() is None:
        return None
    cur.execute(
        """SELECT t.id AS api_token_id, t.user_id, t.household_id, t.scopes,
                  u.email, u.display_name, hm.role AS household_role
        FROM api_tokens t JOIN users u ON u.id = t.user_id
        JOIN household_memberships hm
          ON hm.user_id = t.user_id AND hm.household_id = t.household_id
        WHERE t.token_hash = %s AND t.revoked_at IS NULL
          AND (t.expires_at IS NULL OR t.expires_at > clock_timestamp())
          AND NOT u.is_disabled""",
        (token_hash,),
    )
    row = cur.fetchone()
    if row is not None:
        cur.execute(
            "UPDATE api_tokens SET last_used_at = clock_timestamp() WHERE id = %s "
            "AND (last_used_at IS NULL OR last_used_at < clock_timestamp() - interval '1 minute')",
            (row["api_token_id"],),
        )
    return cast(dict[str, Any] | None, row)
