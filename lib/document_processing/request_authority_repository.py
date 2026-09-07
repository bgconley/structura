"""Actor/credential/resource lock prefix shared by admission and bound publications.

This module has no job imports: enqueue must acquire these locks before job-root
ownership. Database-only job lifecycle checks remain non-locking snapshots.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from lib.auth.authorization_policy import scopes_permit_action
from lib.auth.models import AuthPrincipal
from lib.document_processing.errors import ProcessingAuthorityLost, ProcessingError
from lib.document_processing.models import ProcessingBinding
from lib.document_processing.request_origin import ProcessingOrigin


def admit_request(cur: Any, document_id: UUID, principal: AuthPrincipal) -> ProcessingOrigin:
    origin = ProcessingOrigin.from_principal(principal)
    try:
        _lock_actor(cur, origin, admission=True)
        lock_document_permissions(cur, document_id, origin)
    except ProcessingAuthorityLost:
        raise ProcessingError("Processing request authority is unavailable.") from None
    # Fresh after every lock; never authorize using a predicate evaluated before
    # a wait for reset, membership downgrade, token revoke, or document refiling.
    cur.execute(
        "SELECT document_is_writable(%s, %s, %s, NULL) AS allowed",
        (document_id, origin.household_id, origin.user_id),
    )
    if not cur.fetchone()["allowed"]:
        raise ProcessingError("Document is unavailable for processing.")
    if origin.kind == "session":
        cur.execute(
            """SELECT id FROM sessions WHERE id = %s AND user_id = %s AND household_id = %s
            AND revoked_at IS NULL AND expires_at > clock_timestamp()
            AND csrf_token_hash IS NOT NULL""",
            (origin.session_id, origin.user_id, origin.household_id),
        )
        if cur.fetchone() is None:
            raise ProcessingError("Processing request credential is unavailable.")
        return origin
    cur.execute(
        """SELECT scopes FROM api_tokens WHERE id = %s AND user_id = %s AND household_id = %s
        AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > clock_timestamp())""",
        (origin.api_token_id, origin.user_id, origin.household_id),
    )
    token = cur.fetchone()
    if token is None or not scopes_permit_action(tuple(token["scopes"]), "documents:write"):
        raise ProcessingError("Processing request credential is unavailable.")
    # Record the actual locked credential's ceiling, not a caller's role/scopes.
    return replace(origin, scope_ceiling=tuple(sorted(set(token["scopes"]))))


def lock_processing_request(cur: Any, binding: ProcessingBinding) -> None:
    """Read immutable origin first, then acquire the complete authority prefix."""
    cur.execute(
        """SELECT requested_by_user_id, household_id, origin_kind, origin_session_id,
                  origin_api_token_id, origin_scope_ceiling
        FROM document_processing_runs
        WHERE id = %s AND document_id = %s AND parse_generation_id = %s""",
        (binding.processing_run_id, binding.document_id, binding.parse_generation_id),
    )
    row = cur.fetchone()
    if row is None or row["origin_kind"] not in {"session", "api_token"}:
        raise ProcessingAuthorityLost("Processing request origin is unavailable.")
    origin = ProcessingOrigin(
        row["requested_by_user_id"],
        row["household_id"],
        row["origin_kind"],
        row["origin_session_id"],
        row["origin_api_token_id"],
        tuple(row["origin_scope_ceiling"]),
    )
    _lock_actor(cur, origin, admission=False)
    lock_document_permissions(cur, binding.document_id, origin)


def _lock_actor(cur: Any, origin: ProcessingOrigin, *, admission: bool) -> None:
    # SHARE prevents non-key privilege updates; KEY SHARE alone would not.
    cur.execute("SELECT id FROM households WHERE id = %s FOR KEY SHARE", (origin.household_id,))
    if cur.fetchone() is None:
        raise ProcessingAuthorityLost("Processing household is unavailable.")
    cur.execute("SELECT id FROM users WHERE id = %s FOR SHARE", (origin.user_id,))
    if cur.fetchone() is None:
        raise ProcessingAuthorityLost("Processing actor is unavailable.")
    cur.execute(
        "SELECT user_id FROM household_memberships WHERE household_id = %s AND user_id = %s "
        "FOR SHARE",
        (origin.household_id, origin.user_id),
    )
    if cur.fetchone() is None:
        raise ProcessingAuthorityLost("Processing membership is unavailable.")
    if origin.kind == "api_token":
        cur.execute("SELECT id FROM api_tokens WHERE id = %s FOR SHARE", (origin.api_token_id,))
        if cur.fetchone() is None:
            raise ProcessingAuthorityLost("Processing token is unavailable.")
    elif admission:
        cur.execute("SELECT id FROM sessions WHERE id = %s FOR SHARE", (origin.session_id,))
        if cur.fetchone() is None:
            raise ProcessingAuthorityLost("Processing session is unavailable.")


def lock_document_permissions(cur: Any, document_id: UUID, origin: ProcessingOrigin) -> None:
    cur.execute("SELECT id FROM documents WHERE id = %s FOR UPDATE", (document_id,))
    if cur.fetchone() is None:
        raise ProcessingAuthorityLost("Processing document is unavailable.")
    # Re-read the primary folder after acquiring the document lock.
    cur.execute("SELECT primary_folder_id FROM documents WHERE id = %s", (document_id,))
    folder_id = cur.fetchone()["primary_folder_id"]
    if folder_id is not None:
        cur.execute("SELECT id FROM folders WHERE id = %s FOR SHARE", (folder_id,))
        cur.fetchone()
        cur.execute(
            """SELECT id FROM folder_acl WHERE folder_id = %s
            AND ((principal_type = 'user' AND principal_id = %s)
              OR (principal_type = 'household' AND principal_id = %s))
            ORDER BY id FOR SHARE""",
            (folder_id, origin.user_id, origin.household_id),
        )
        cur.fetchall()
