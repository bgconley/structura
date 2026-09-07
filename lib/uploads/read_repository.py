"""Actor-owned observations with fresh document ACL filtering; no storage paths."""

from typing import Any
from uuid import UUID

from lib.auth.request_authority import RequestCredential
from lib.auth.request_authority_repository import assert_request_authority, lock_request_authority
from lib.uploads.errors import UploadUnavailable
from lib.uploads.models import (
    UploadAttempt,
    UploadCreate,
    UploadDuplicate,
    UploadFailure,
    UploadReceipt,
)
from lib.uploads.public_errors import MESSAGES
from lib.uploads.transactions import upload_connection


def readable_matches(
    cur: Any, credential: RequestCredential, sha256: str
) -> tuple[UploadDuplicate, ...]:
    cur.execute(
        """SELECT d.id,d.title FROM documents d JOIN document_assets a
        ON a.id=d.canonical_asset_id AND a.document_id=d.id AND a.asset_role='original'
        WHERE d.household_id=%s AND d.original_sha256=%s AND a.sha256=%s
          AND d.deleted_at IS NULL AND document_is_readable(d.id,%s,%s,NULL)
        ORDER BY d.created_at,d.id LIMIT 20""",
        (credential.household_id, sha256, sha256, credential.household_id, credential.user_id),
    )
    return tuple(UploadDuplicate(document_id=r["id"], title=r["title"]) for r in cur.fetchall())


def map_attempt(cur: Any, row: dict[str, Any], credential: RequestCredential) -> UploadAttempt:
    metadata = UploadCreate.model_validate(row["metadata_json"])
    receipt = UploadReceipt.model_validate(row["receipt_json"]) if row["receipt_json"] else None
    if receipt:
        cur.execute(
            """SELECT id FROM documents WHERE id=%s AND household_id=%s
            AND document_is_readable(id,%s,%s,NULL)""",
            (
                receipt.document_id,
                credential.household_id,
                credential.household_id,
                credential.user_id,
            ),
        )
        if cur.fetchone() is None:
            raise UploadUnavailable()
    duplicates: tuple[UploadDuplicate, ...] = ()
    if row["state"] == "awaiting_duplicate_decision":
        duplicates = readable_matches(cur, credential, row["content_sha256"])
    return UploadAttempt(
        upload_id=row["id"],
        operation_id=metadata.operation_id,
        client_batch_id=metadata.client_batch_id,
        revision=row["revision"],
        state=row["state"],
        filename=metadata.filename,
        declared_bytes=metadata.declared_bytes,
        actual_bytes=row["content_bytes"],
        sha256=row["content_sha256"],
        detected_mime_type=row["detected_mime_type"],
        current_transfer_id=row["current_transfer_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        receipt=receipt,
        duplicates=duplicates,
        error=UploadFailure(code=row["error_code"], message=MESSAGES[row["error_code"]])
        if row.get("error_code") in MESSAGES
        else None,
    )


def read_attempt(upload_id: UUID, credential: RequestCredential) -> UploadAttempt:
    with upload_connection() as conn, conn.cursor() as cur:
        lock_request_authority(cur, credential, "documents:read")
        cur.execute(
            "SELECT * FROM upload_attempts WHERE id=%s AND household_id=%s AND actor_user_id=%s",
            (upload_id, credential.household_id, credential.user_id),
        )
        row = cur.fetchone()
        if row is None:
            raise UploadUnavailable()
        result = map_attempt(cur, row, credential)
        assert_request_authority(cur, credential, "documents:read")
        return result
