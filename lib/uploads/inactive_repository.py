"""Expire abandoned registration/retry slots without erasing operation identity."""

from typing import Any
from uuid import UUID

from lib.uploads.authority_repository import ADMISSION_LOCK
from lib.uploads.transactions import upload_connection


def expire_inactive_with_cursor(
    cur: Any, *, actor_id: UUID | None = None, limit: int = 1000
) -> int:
    """Caller holds global admission lock; no locks or quota releases for live IO."""
    cur.execute(
        """WITH expired AS (SELECT id FROM upload_attempts
        WHERE state='awaiting_content' AND inactive_expires_at<=clock_timestamp()
        AND (%s::uuid IS NULL OR actor_user_id=%s)
        AND NOT EXISTS (SELECT 1 FROM upload_transfers t WHERE t.upload_id=upload_attempts.id
          AND t.cleanup_confirmed_at IS NULL AND (t.io_stopped_at IS NULL
            OR (t.held_until>clock_timestamp() AND t.revoked_at IS NULL)))
        ORDER BY id LIMIT %s FOR UPDATE)
        UPDATE upload_attempts a SET state='expired',revision=gen_random_uuid(),
        updated_at=clock_timestamp() FROM expired WHERE a.id=expired.id RETURNING a.id""",
        (actor_id, actor_id, limit),
    )
    identities = [row["id"] for row in cur.fetchall()]
    if identities:
        cur.execute(
            """UPDATE upload_transfers SET revoked_at=COALESCE(revoked_at,clock_timestamp())
            WHERE upload_id=ANY(%s::uuid[]) AND cleanup_confirmed_at IS NULL""",
            (identities,),
        )
    return len(identities)


def expire_inactive_attempts(*, limit: int = 100) -> int:
    if not 1 <= limit <= 100:
        raise ValueError("Inactive expiry batch must be bounded.")
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADMISSION_LOCK,))
        result = expire_inactive_with_cursor(cur, limit=limit)
        conn.commit()
        return result
