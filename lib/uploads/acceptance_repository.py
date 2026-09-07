"""Atomic original/document/jobs/receipt acceptance using shared intake repositories."""

from typing import Any

from psycopg.types.json import Jsonb

from lib.auth.request_authority_repository import assert_request_authority
from lib.documents.ingestion_content import safe_original_filename, title_from_filename
from lib.documents.ingestion_jobs import create_ingestion_jobs
from lib.documents.ingestion_models import DocumentIngestionRequest
from lib.documents.ingestion_repository import (
    attach_original_asset,
    create_ingest_batch,
    create_original_document,
)
from lib.storage import lock_content_hash
from lib.storage.verified_publication import PreparedOriginal
from lib.uploads.authority_repository import fence_transfer, lock_prefix, lock_transfer, require_row
from lib.uploads.duplicate_repository import lock_exact_duplicate
from lib.uploads.errors import UploadConflict, UploadUnavailable
from lib.uploads.models import (
    TransferLease,
    UploadAttempt,
    UploadDecision,
    UploadReceipt,
    VerifiedContent,
)
from lib.uploads.policy import UploadPolicy
from lib.uploads.read_repository import map_attempt, readable_matches
from lib.uploads.transactions import upload_connection


def _require_verified_source(
    cur: Any, lease: TransferLease, prepared: PreparedOriginal, content: VerifiedContent
) -> None:
    cur.execute(
        """SELECT id FROM upload_transfers WHERE id=%s AND upload_id=%s
        AND verified_at IS NOT NULL AND content_sha256=%s AND content_bytes=%s
        AND detected_mime_type=%s AND cleanup_confirmed_at IS NULL AND revoked_at IS NULL
        AND (%s OR held_until>clock_timestamp())""",
        (
            lease.source_transfer_id,
            lease.upload_id,
            prepared.content.sha256,
            prepared.content.byte_size,
            content.mime_type,
            lease.kind != "decision",
        ),
    )
    if cur.fetchone() is None:
        raise UploadConflict()


def _new_receipt(
    cur: Any, lease: TransferLease, prepared: PreparedOriginal, content: VerifiedContent
) -> UploadReceipt:
    meta = lease.metadata
    name = safe_original_filename(meta.filename)
    title = meta.title.strip() if meta.title and meta.title.strip() else title_from_filename(name)
    request = DocumentIngestionRequest(
        household_id=lease.credential.household_id,
        owner_user_id=lease.credential.user_id,
        source=meta.source,
        filename=name,
        declared_mime_type=content.mime_type,
        supplied_title=title,
        hints={},
        requested_by=str(lease.credential.user_id),
    )
    batch_id = create_ingest_batch(cur, source=meta.source, original_name=name, hints={})
    document_id = create_original_document(
        cur,
        request=request,
        batch_id=batch_id,
        title=title,
        original_name=name,
        sha256=prepared.content.sha256,
        mime_type=content.mime_type,
        byte_size=prepared.content.byte_size,
        duplicate_id=None,
    )
    # New document row is owned by this transaction. Never take content before it.
    lock_content_hash(cur, prepared.content.sha256)
    stored = prepared.commit()
    asset_id = attach_original_asset(
        cur,
        document_id=document_id,
        stored=stored,
        mime_type=content.mime_type,
        original_name=name,
    )
    job = create_ingestion_jobs(
        cur,
        household_id=lease.credential.household_id,
        document_id=document_id,
        batch_id=batch_id,
        asset_id=asset_id,
        stored=stored,
        mime_type=content.mime_type,
        filename=name,
        source=meta.source,
        hints={},
        requested_by=str(lease.credential.user_id),
        duplicate_id=None,
    )
    cur.execute("SELECT clock_timestamp() AS at")
    return UploadReceipt(
        outcome="accepted",
        document_id=document_id,
        asset_id=asset_id,
        batch_id=batch_id,
        job_id=job.job_id,
        sha256=prepared.content.sha256,
        byte_size=prepared.content.byte_size,
        recorded_at=require_row(cur)["at"],
    )


def finish_transfer(
    lease: TransferLease,
    prepared: PreparedOriginal,
    content: VerifiedContent,
    policy: UploadPolicy,
    *,
    decision: UploadDecision | None = None,
) -> UploadAttempt:
    if (lease.kind == "decision") != (decision is not None):
        raise UploadConflict()
    if (content.sha256, content.byte_size) != (prepared.content.sha256, prepared.content.byte_size):
        raise UploadConflict()
    with upload_connection() as conn, conn.cursor() as cur:
        lock_prefix(cur, lease.credential, prepared.content.sha256)
        row = lock_transfer(cur, lease)
        _require_verified_source(cur, lease, prepared, content)
        if (
            row["content_sha256"] != prepared.content.sha256
            or row["content_bytes"] != prepared.content.byte_size
        ):
            raise UploadConflict()
        if row["receipt_json"]:
            # Received-content equality has already been independently verified.
            result = map_attempt(cur, row, lease.credential)
            fence_transfer(cur, lease)
            conn.commit()
            return result
        if decision is None and readable_matches(cur, lease.credential, prepared.content.sha256):
            cur.execute(
                """UPDATE upload_transfers SET held_until=clock_timestamp()+make_interval(secs=>%s)
                WHERE id=%s""",
                (policy.held_seconds, lease.transfer_id),
            )
            cur.execute(
                """UPDATE upload_attempts SET state='awaiting_duplicate_decision',
                revision=gen_random_uuid(),updated_at=clock_timestamp() WHERE id=%s RETURNING *""",
                (lease.upload_id,),
            )
            row = require_row(cur)
            result = map_attempt(cur, row, lease.credential)
            fence_transfer(cur, lease)
            conn.commit()
            return result
        if decision and decision.decision == "use_existing":
            if decision.document_id is None or prepared.existing_identity is None:
                raise UploadUnavailable()
            original = lock_exact_duplicate(
                cur,
                decision.document_id,
                lease.credential,
                content,
                prepared.uri,
            )
            lock_content_hash(cur, prepared.content.sha256)
            if not prepared.path.exists():
                raise UploadUnavailable()
            prepared.commit()
            cur.execute("SELECT clock_timestamp() AS at")
            receipt = UploadReceipt(
                outcome="reused",
                document_id=decision.document_id,
                asset_id=original["asset_id"],
                sha256=prepared.content.sha256,
                byte_size=prepared.content.byte_size,
                recorded_at=require_row(cur)["at"],
            )
        else:
            receipt = _new_receipt(cur, lease, prepared, content)
        cur.execute(
            """UPDATE upload_attempts SET state=%s,receipt_json=%s::jsonb,
            revision=gen_random_uuid(),updated_at=clock_timestamp() WHERE id=%s RETURNING *""",
            (receipt.outcome, Jsonb(receipt.model_dump(mode="json")), lease.upload_id),
        )
        row = require_row(cur)
        result = map_attempt(cur, row, lease.credential)
        _require_verified_source(cur, lease, prepared, content)
        fence_transfer(cur, lease)
        assert_request_authority(cur, lease.credential, "documents:write")
        conn.commit()
        return result
