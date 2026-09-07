"""Live request credential prefix and fresh capability checks in caller transactions.

Lock before any document/attempt/domain row. Call assert_request_authority again
after all waits/fences, immediately before commit: row locks cannot stop time from
expiring a credential. Already admitted browser jobs intentionally do not use this.
"""

from typing import Any

from lib.auth.authorization_policy import Action, AuthorizationError, scopes_permit_action
from lib.auth.request_authority import RequestCredential


def lock_request_authority(cur: Any, credential: RequestCredential, action: Action) -> None:
    cur.execute("SELECT id FROM households WHERE id=%s FOR KEY SHARE", (credential.household_id,))
    _require_row(cur)
    cur.execute("SELECT id FROM users WHERE id=%s FOR SHARE", (credential.user_id,))
    _require_row(cur)
    cur.execute(
        "SELECT user_id FROM household_memberships WHERE household_id=%s AND user_id=%s FOR SHARE",
        (credential.household_id, credential.user_id),
    )
    _require_row(cur)
    if credential.kind == "session":
        cur.execute("SELECT id FROM sessions WHERE id=%s FOR SHARE", (credential.session_id,))
    else:
        cur.execute("SELECT id FROM api_tokens WHERE id=%s FOR SHARE", (credential.api_token_id,))
    _require_row(cur)
    assert_request_authority(cur, credential, action)


def assert_request_authority(cur: Any, credential: RequestCredential, action: Action) -> None:
    """Fresh SQL after lock waits; caller must retain lock_request_authority locks."""
    cur.execute(
        """SELECT hm.role FROM users u JOIN household_memberships hm ON hm.user_id=u.id
        WHERE u.id=%s AND hm.household_id=%s AND NOT u.is_disabled""",
        (credential.user_id, credential.household_id),
    )
    member = cur.fetchone()
    roles = {"owner", "admin"}
    if action in {"documents:write", "documents:review"}:
        roles.add("member")
    elif action == "documents:read":
        roles.update({"member", "viewer"})
    if member is None or member["role"] not in roles:
        raise AuthorizationError("Permission denied")
    if credential.kind == "session":
        cur.execute(
            """SELECT id FROM sessions WHERE id=%s AND user_id=%s AND household_id=%s
            AND revoked_at IS NULL AND expires_at>clock_timestamp() AND
            csrf_token_hash IS NOT NULL""",
            (credential.session_id, credential.user_id, credential.household_id),
        )
        _require_row(cur)
        return
    cur.execute(
        """SELECT scopes FROM api_tokens WHERE id=%s AND user_id=%s AND household_id=%s
        AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp())""",
        (credential.api_token_id, credential.user_id, credential.household_id),
    )
    token = cur.fetchone()
    if (
        token is None
        or not scopes_permit_action(tuple(token["scopes"]), action)
        or not scopes_permit_action(credential.scope_ceiling, action)
    ):
        raise AuthorizationError("Permission denied")


def _require_row(cur: Any) -> None:
    if cur.fetchone() is None:
        raise AuthorizationError("Permission denied")
