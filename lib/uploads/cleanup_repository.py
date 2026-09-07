"""Cleanup claims retain byte reservations until the exact source lock proves IO stopped."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from lib.uploads.authority_repository import ADMISSION_LOCK, require_row
from lib.uploads.errors import UploadConflict
from lib.uploads.policy import UploadPolicy
from lib.uploads.transactions import upload_connection


@dataclass(frozen=True)
class CleanupClaim:
    upload_id: UUID
    transfer_id: UUID
    token: UUID
    content_sha256: str | None
    content_bytes: int | None


def claim_cleanup(transfer_id: UUID, policy: UploadPolicy) -> CleanupClaim | None:
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADMISSION_LOCK,))
        cur.execute("SELECT upload_id FROM upload_transfers WHERE id=%s", (transfer_id,))
        row = cur.fetchone()
        if not row:
            return None
        upload_id = row["upload_id"]
        cur.execute("SELECT * FROM upload_attempts WHERE id=%s FOR UPDATE", (upload_id,))
        operation = require_row(cur)
        cur.execute("SELECT * FROM upload_transfers WHERE id=%s FOR UPDATE", (transfer_id,))
        transfer = require_row(cur)
        token = uuid4()
        cur.execute(
            """UPDATE upload_transfers SET cleanup_token=%s,
            cleanup_expires_at=clock_timestamp()+make_interval(secs=>%s),
            revoked_at=COALESCE(revoked_at,clock_timestamp())
            WHERE id=%s AND cleanup_confirmed_at IS NULL
              AND (cleanup_token IS NULL OR cleanup_expires_at<=clock_timestamp())
              AND (revoked_at IS NOT NULL OR
                (held_until IS NOT NULL AND held_until<=clock_timestamp()) OR
                (held_until IS NULL AND lease_expires_at<=clock_timestamp())) RETURNING id""",
            (token, policy.cleanup_lease_seconds, transfer_id),
        )
        if not cur.fetchone():
            return None
        # A failed decision's zero-byte lease is not the held source. Reclaiming
        # that decision must not expire still-valid staged bytes or their operation.
        if transfer["kind"] != "decision" and operation["state"] in {
            "receiving",
            "awaiting_duplicate_decision",
        }:
            state = "expired" if transfer["held_until"] is not None else "awaiting_content"
            cur.execute(
                """UPDATE upload_attempts a SET state=%s,revision=gen_random_uuid(),
                inactive_expires_at=clock_timestamp()+make_interval(secs=>%s),
                updated_at=clock_timestamp() WHERE a.id=%s AND
                (a.current_transfer_id=%s OR EXISTS (SELECT 1 FROM upload_transfers current
                    WHERE current.id=a.current_transfer_id AND current.kind='decision'
                    AND current.source_transfer_id=%s))""",
                (state, policy.inactive_seconds, upload_id, transfer_id, transfer_id),
            )
        conn.commit()
        return CleanupClaim(
            upload_id, transfer_id, token, transfer["content_sha256"], transfer["content_bytes"]
        )


def finish_cleanup(claim: CleanupClaim) -> None:
    """Caller has removed data and fsynced the directory while holding its OS lock."""
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADMISSION_LOCK,))
        cur.execute("SELECT id FROM upload_attempts WHERE id=%s FOR UPDATE", (claim.upload_id,))
        cur.execute("SELECT id FROM upload_transfers WHERE id=%s FOR UPDATE", (claim.transfer_id,))
        cur.execute(
            """UPDATE upload_transfers SET cleanup_confirmed_at=clock_timestamp(),
            io_stopped_at=COALESCE(io_stopped_at,clock_timestamp()) WHERE id=%s
            AND cleanup_token=%s AND cleanup_confirmed_at IS NULL
            AND cleanup_expires_at>clock_timestamp() AND revoked_at IS NOT NULL RETURNING id""",
            (claim.transfer_id, claim.token),
        )
        if not cur.fetchone():
            raise UploadConflict()
        conn.commit()


def cleanup_candidates(*, limit: int = 100) -> tuple[UUID, ...]:
    if not 1 <= limit <= 100:
        raise ValueError("Cleanup batch must be bounded.")
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM upload_transfers WHERE cleanup_confirmed_at IS NULL
            AND (cleanup_token IS NULL OR cleanup_expires_at<=clock_timestamp())
            AND (revoked_at IS NOT NULL OR
              (held_until IS NOT NULL AND held_until<=clock_timestamp()) OR
              (held_until IS NULL AND lease_expires_at<=clock_timestamp()))
            ORDER BY (cleanup_token IS NOT NULL),cleanup_expires_at NULLS FIRST,created_at,id
            LIMIT %s""",
            (limit,),
        )
        return tuple(row["id"] for row in cur.fetchall())
