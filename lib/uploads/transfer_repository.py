"""Leased admission and IO state. Expiry/revocation never frees uncollected bytes."""

from typing import Any, Literal
from uuid import UUID, uuid4

from lib.auth.request_authority import RequestCredential
from lib.uploads.authority_repository import (
    credential_json,
    fence_transfer,
    lock_attempt,
    lock_prefix,
    lock_transfer,
    require_row,
)
from lib.uploads.errors import UploadCapacity, UploadConflict
from lib.uploads.inactive_repository import expire_inactive_with_cursor
from lib.uploads.models import TransferLease, UploadCreate, VerifiedContent
from lib.uploads.policy import UploadPolicy
from lib.uploads.transactions import upload_connection


def _capacity(cur: Any, credential: RequestCredential, size: int, policy: UploadPolicy) -> None:
    cur.execute(
        """SELECT count(*) FILTER (WHERE t.io_stopped_at IS NULL) AS active,
        count(*) FILTER (WHERE t.io_stopped_at IS NULL AND a.actor_user_id=%s) AS actor_active,
        COALESCE(sum(t.reserved_bytes),0) AS bytes,
        COALESCE(sum(t.reserved_bytes) FILTER (WHERE a.actor_user_id=%s),0) AS actor_bytes
        FROM upload_transfers t JOIN upload_attempts a ON a.id=t.upload_id
        WHERE t.cleanup_confirmed_at IS NULL""",
        (credential.user_id, credential.user_id),
    )
    usage = cur.fetchone()
    if (
        usage["active"] >= policy.global_active_limit
        or usage["actor_active"] >= policy.actor_active_limit
        or usage["bytes"] + size > policy.global_reserved_bytes
        or usage["actor_bytes"] + size > policy.actor_reserved_bytes
    ):
        raise UploadCapacity()


def reserve_transfer(
    upload_id: UUID,
    revision: UUID,
    credential: RequestCredential,
    policy: UploadPolicy,
    *,
    replace_transfer_id: UUID | None = None,
    decision: bool = False,
) -> TransferLease:
    with upload_connection() as conn, conn.cursor() as cur:
        lock_prefix(cur, credential)
        expire_inactive_with_cursor(cur, actor_id=credential.user_id)
        row = lock_attempt(cur, upload_id, credential)
        if row["revision"] != revision or row["state"] in {"cancelled", "expired", "rejected"}:
            raise UploadConflict()
        metadata = UploadCreate.model_validate(row["metadata_json"])
        source_id = row["current_transfer_id"]
        previous = None
        if source_id:
            cur.execute("SELECT * FROM upload_transfers WHERE id=%s FOR UPDATE", (source_id,))
            previous = cur.fetchone()
        if decision:
            if previous and previous["kind"] == "decision":
                source_id = previous["source_transfer_id"]
            if row["state"] != "awaiting_duplicate_decision" or not previous:
                raise UploadConflict()
            cur.execute(
                """SELECT id FROM upload_transfers WHERE id=%s AND verified_at IS NOT NULL
                AND revoked_at IS NULL AND cleanup_confirmed_at IS NULL
                AND held_until>clock_timestamp()""",
                (source_id,),
            )
            if cur.fetchone() is None:
                raise UploadConflict()
        elif row["state"] in {"receiving", "awaiting_duplicate_decision"}:
            if replace_transfer_id != source_id:
                raise UploadConflict()
        elif previous and previous["cleanup_confirmed_at"] is None and row["receipt_json"] is None:
            if replace_transfer_id != source_id:
                raise UploadConflict()
        elif replace_transfer_id is not None and replace_transfer_id != source_id:
            raise UploadConflict()
        if row["state"] == "awaiting_content":
            cur.execute(
                """SELECT id FROM upload_attempts WHERE id=%s
                AND inactive_expires_at>clock_timestamp()""",
                (upload_id,),
            )
            if cur.fetchone() is None:
                raise UploadConflict()
        kind: Literal["receive", "replay", "decision"] = (
            "decision" if decision else "replay" if row["receipt_json"] else "receive"
        )
        size = 0 if decision else metadata.declared_bytes
        _capacity(cur, credential, size, policy)
        if previous and not decision and previous["cleanup_confirmed_at"] is None:
            cur.execute(
                """UPDATE upload_transfers SET revoked_at=COALESCE(revoked_at,clock_timestamp())
                WHERE id=%s""",
                (source_id,),
            )
        transfer_id, owner_token = uuid4(), uuid4()
        generation = row["generation"] + 1
        source_id = source_id if decision else transfer_id
        cur.execute(
            """INSERT INTO upload_transfers(id,upload_id,generation,owner_token,kind,
            credential_json,source_transfer_id,reserved_bytes,lease_expires_at,deadline_at)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,
            clock_timestamp()+make_interval(secs=>%s),clock_timestamp()+make_interval(secs=>%s))
            RETURNING deadline_at""",
            (
                transfer_id,
                upload_id,
                generation,
                owner_token,
                kind,
                credential_json(credential),
                source_id,
                size,
                policy.lease_seconds,
                policy.absolute_seconds,
            ),
        )
        deadline_at = require_row(cur)["deadline_at"]
        cur.execute(
            """UPDATE upload_attempts SET current_transfer_id=%s,generation=%s,
            revision=gen_random_uuid(),updated_at=clock_timestamp(),
            state=CASE WHEN receipt_json IS NOT NULL THEN state ELSE 'receiving' END
            WHERE id=%s""",
            (transfer_id, generation, upload_id),
        )
        lease = TransferLease(
            upload_id,
            transfer_id,
            generation,
            owner_token,
            credential,
            metadata,
            kind,
            source_id,
            deadline_at,
        )
        fence_transfer(cur, lease)
        conn.commit()
        return lease


def renew_transfer(
    lease: TransferLease, policy: UploadPolicy, *, require_open: bool = True
) -> None:
    with upload_connection() as conn, conn.cursor() as cur:
        lock_prefix(cur, lease.credential)
        lock_transfer(cur, lease)
        fence_transfer(cur, lease, require_open=require_open)
        cur.execute(
            """UPDATE upload_transfers SET lease_expires_at=LEAST(deadline_at,
            clock_timestamp()+make_interval(secs=>%s)) WHERE id=%s""",
            (policy.lease_seconds, lease.transfer_id),
        )
        fence_transfer(cur, lease, require_open=require_open)
        conn.commit()


def record_verified(lease: TransferLease, content: VerifiedContent) -> None:
    with upload_connection() as conn, conn.cursor() as cur:
        lock_prefix(cur, lease.credential)
        row = lock_transfer(cur, lease)
        fence_transfer(cur, lease, require_open=True)
        if row["content_sha256"] is not None and (
            row["content_sha256"],
            row["content_bytes"],
            row["detected_mime_type"],
        ) != (content.sha256, content.byte_size, content.mime_type):
            raise UploadConflict()
        cur.execute(
            """UPDATE upload_transfers SET verified_at=clock_timestamp(),
            io_stopped_at=clock_timestamp(),content_sha256=%s,content_bytes=%s,detected_mime_type=%s
            WHERE id=%s""",
            (content.sha256, content.byte_size, content.mime_type, lease.transfer_id),
        )
        cur.execute(
            """UPDATE upload_attempts SET content_sha256=%s,content_bytes=%s,detected_mime_type=%s,
            updated_at=clock_timestamp() WHERE id=%s""",
            (content.sha256, content.byte_size, content.mime_type, lease.upload_id),
        )
        fence_transfer(cur, lease)
        conn.commit()


def abandon_transfer(lease: TransferLease, policy: UploadPolicy) -> None:
    """Called only after writer IO stopped, including disconnect/credential failure.

    This revokes execution, but cleanup must separately prove byte reclamation.
    No live credential is required to stop one's exact internal ownership token.
    """
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM upload_attempts WHERE id=%s FOR UPDATE", (lease.upload_id,))
        cur.execute(
            """UPDATE upload_transfers SET io_stopped_at=COALESCE(io_stopped_at,clock_timestamp()),
            revoked_at=COALESCE(revoked_at,clock_timestamp()) WHERE id=%s AND owner_token=%s
            AND cleanup_confirmed_at IS NULL""",
            (lease.transfer_id, lease.owner_token),
        )
        cur.execute(
            """UPDATE upload_attempts SET state=%s,revision=gen_random_uuid(),
            inactive_expires_at=clock_timestamp()+make_interval(secs=>%s),
            updated_at=clock_timestamp() WHERE id=%s AND current_transfer_id=%s
            AND state='receiving' AND receipt_json IS NULL""",
            (
                "awaiting_duplicate_decision" if lease.kind == "decision" else "awaiting_content",
                policy.inactive_seconds,
                lease.upload_id,
                lease.transfer_id,
            ),
        )
        conn.commit()


def reject_transfer(lease: TransferLease, code: str) -> None:
    """Only static content rejection, never operational errors or accepted replay."""
    from lib.uploads.public_errors import MESSAGES

    if code not in MESSAGES:
        return
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM upload_attempts WHERE id=%s FOR UPDATE", (lease.upload_id,))
        cur.execute(
            """UPDATE upload_attempts a SET state='rejected',error_code=%s,
            revision=gen_random_uuid(),updated_at=clock_timestamp()
            WHERE a.id=%s AND a.current_transfer_id=%s AND a.state='receiving'
            AND a.receipt_json IS NULL AND EXISTS (SELECT 1 FROM upload_transfers t
              WHERE t.id=a.current_transfer_id AND t.owner_token=%s)""",
            (code, lease.upload_id, lease.transfer_id, lease.owner_token),
        )
        conn.commit()


def held_content(lease: TransferLease) -> VerifiedContent:
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT content_sha256,content_bytes,detected_mime_type FROM upload_transfers
            WHERE id=%s AND upload_id=%s AND verified_at IS NOT NULL
              AND cleanup_confirmed_at IS NULL AND revoked_at IS NULL
              AND held_until>clock_timestamp()""",
            (lease.source_transfer_id, lease.upload_id),
        )
        row = cur.fetchone()
        if not row:
            raise UploadConflict()
        return VerifiedContent(
            row["content_sha256"], row["content_bytes"], row["detected_mime_type"]
        )


def revoke_source(lease: TransferLease) -> None:
    with upload_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE upload_transfers SET revoked_at=COALESCE(revoked_at,clock_timestamp())
            WHERE id=%s AND upload_id=%s AND cleanup_confirmed_at IS NULL""",
            (lease.source_transfer_id, lease.upload_id),
        )
        conn.commit()
