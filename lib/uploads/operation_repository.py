"""Operation registration and cancellation keep permanent idempotency tombstones."""

from uuid import UUID

from psycopg.types.json import Jsonb

from lib.auth.request_authority import RequestCredential
from lib.auth.request_authority_repository import assert_request_authority
from lib.uploads.authority_repository import lock_attempt, lock_prefix, require_row
from lib.uploads.errors import UploadCapacity, UploadConflict, UploadError
from lib.uploads.inactive_repository import expire_inactive_with_cursor
from lib.uploads.models import UploadAttempt, UploadCreate
from lib.uploads.policy import UploadPolicy
from lib.uploads.read_repository import map_attempt
from lib.uploads.transactions import upload_connection


def create_attempt(
    metadata: UploadCreate, credential: RequestCredential, policy: UploadPolicy
) -> UploadAttempt:
    if metadata.declared_bytes > policy.max_file_bytes:
        raise UploadError("upload_too_large")
    document = metadata.model_dump(mode="json")
    with upload_connection() as conn, conn.cursor() as cur:
        lock_prefix(cur, credential)
        expire_inactive_with_cursor(cur, actor_id=credential.user_id)
        cur.execute(
            """SELECT * FROM upload_attempts WHERE household_id=%s AND actor_user_id=%s
            AND operation_id=%s FOR UPDATE""",
            (credential.household_id, credential.user_id, metadata.operation_id),
        )
        row = cur.fetchone()
        if row:
            if row["metadata_json"] != document:
                raise UploadConflict()
        else:
            cur.execute(
                """SELECT count(*) AS n FROM upload_attempts WHERE actor_user_id=%s
                AND state IN ('awaiting_content','receiving','awaiting_duplicate_decision')""",
                (credential.user_id,),
            )
            if require_row(cur)["n"] >= policy.queue_reference_limit:
                raise UploadCapacity()
            cur.execute(
                """INSERT INTO upload_attempts
                (household_id,actor_user_id,operation_id,metadata_json,inactive_expires_at)
                VALUES (%s,%s,%s,%s::jsonb,clock_timestamp()+make_interval(secs=>%s))
                RETURNING *""",
                (
                    credential.household_id,
                    credential.user_id,
                    metadata.operation_id,
                    Jsonb(document),
                    policy.inactive_seconds,
                ),
            )
            row = require_row(cur)
        result = map_attempt(cur, row, credential)
        assert_request_authority(cur, credential, "documents:write")
        conn.commit()
        return result


def cancel_attempt(upload_id: UUID, credential: RequestCredential) -> UploadAttempt:
    with upload_connection() as conn, conn.cursor() as cur:
        lock_prefix(cur, credential)
        row = lock_attempt(cur, upload_id, credential)
        if row["state"] not in {"accepted", "reused", "cancelled", "expired", "rejected"}:
            cur.execute(
                """UPDATE upload_attempts SET state='cancelled',revision=gen_random_uuid(),
                updated_at=clock_timestamp() WHERE id=%s RETURNING *""",
                (upload_id,),
            )
            row = require_row(cur)
            cur.execute(
                """UPDATE upload_transfers SET revoked_at=COALESCE(revoked_at,clock_timestamp())
                WHERE upload_id=%s AND cleanup_confirmed_at IS NULL""",
                (upload_id,),
            )
        result = map_attempt(cur, row, credential)
        assert_request_authority(cur, credential, "documents:write")
        conn.commit()
        return result
