"""Upload lock prefix and exact captured-credential/lease fences."""

from dataclasses import asdict
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.auth.request_authority import RequestCredential
from lib.auth.request_authority_repository import assert_request_authority, lock_request_authority
from lib.documents.ingestion_admission import lock_original_admission
from lib.uploads.errors import UploadConflict, UploadStorageUnavailable, UploadUnavailable
from lib.uploads.models import TransferLease

# Separate namespace from original admission and content cleanup. Always first.
ADMISSION_LOCK = 761166780410021047


def lock_prefix(cur: Any, credential: RequestCredential, content_hash: str | None = None) -> None:
    cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADMISSION_LOCK,))
    if content_hash is not None:
        lock_original_admission(cur, credential.household_id, content_hash)
    lock_request_authority(cur, credential, "documents:write")


def lock_attempt(cur: Any, upload_id: UUID, credential: RequestCredential) -> dict[str, Any]:
    cur.execute(
        """SELECT * FROM upload_attempts WHERE id=%s AND household_id=%s
        AND actor_user_id=%s FOR UPDATE""",
        (upload_id, credential.household_id, credential.user_id),
    )
    row = cur.fetchone()
    if row is None:
        raise UploadUnavailable()
    return cast(dict[str, Any], row)


def credential_json(credential: RequestCredential) -> Jsonb:
    values = asdict(credential)
    return Jsonb(
        {key: str(value) if isinstance(value, UUID) else value for key, value in values.items()}
    )


def fence_transfer(cur: Any, lease: TransferLease, *, require_open: bool = False) -> dict[str, Any]:
    """Prefix locks must already be held; fresh clock checks after every later wait."""
    assert_request_authority(cur, lease.credential, "documents:write")
    cur.execute(
        """SELECT t.* FROM upload_transfers t JOIN upload_attempts a ON a.id=t.upload_id
        WHERE t.id=%s AND t.upload_id=%s AND t.owner_token=%s AND t.generation=%s
          AND a.current_transfer_id=t.id AND a.generation=t.generation
          AND a.state NOT IN ('cancelled','expired','rejected') AND t.revoked_at IS NULL
          AND t.cleanup_confirmed_at IS NULL AND t.lease_expires_at>clock_timestamp()
          AND t.deadline_at>clock_timestamp() AND (NOT %s OR t.io_stopped_at IS NULL)
          AND t.credential_json=%s::jsonb AND a.metadata_json=%s::jsonb
          AND t.source_transfer_id=%s AND t.kind=%s""",
        (
            lease.transfer_id,
            lease.upload_id,
            lease.owner_token,
            lease.generation,
            require_open,
            credential_json(lease.credential),
            Jsonb(lease.metadata.model_dump(mode="json")),
            lease.source_transfer_id,
            lease.kind,
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise UploadConflict()
    return cast(dict[str, Any], row)


def lock_transfer(cur: Any, lease: TransferLease) -> dict[str, Any]:
    row = lock_attempt(cur, lease.upload_id, lease.credential)
    cur.execute("SELECT id FROM upload_transfers WHERE id=%s FOR UPDATE", (lease.transfer_id,))
    if cur.fetchone() is None:
        raise UploadConflict()
    fence_transfer(cur, lease)
    return row


def require_row(cur: Any) -> dict[str, Any]:
    """Required write/count result; no caller data in failure diagnostics."""
    row = cur.fetchone()
    if row is None:
        raise UploadStorageUnavailable()
    return cast(dict[str, Any], row)
