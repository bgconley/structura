"""Exact readable duplicate selection, locked against refiling and ACL revocation."""

from typing import Any, cast
from uuid import UUID

from lib.auth.request_authority import RequestCredential
from lib.uploads.errors import UploadUnavailable
from lib.uploads.models import VerifiedContent


def lock_exact_duplicate(
    cur: Any,
    document_id: UUID,
    credential: RequestCredential,
    content: VerifiedContent,
    uri: str,
) -> dict[str, Any]:
    cur.execute("SELECT primary_folder_id FROM documents WHERE id=%s FOR UPDATE", (document_id,))
    if cur.fetchone() is None:
        raise UploadUnavailable()
    # Re-read after the document lock wait; the original SELECT snapshot may be old.
    cur.execute("SELECT primary_folder_id FROM documents WHERE id=%s", (document_id,))
    folder_id = cur.fetchone()["primary_folder_id"]
    if folder_id:
        cur.execute("SELECT id FROM folders WHERE id=%s FOR SHARE", (folder_id,))
        cur.fetchall()
        cur.execute(
            """SELECT id FROM folder_acl WHERE folder_id=%s AND
            ((principal_type='user' AND principal_id=%s) OR
             (principal_type='household' AND principal_id=%s)) ORDER BY id FOR SHARE""",
            (folder_id, credential.user_id, credential.household_id),
        )
        cur.fetchall()
    cur.execute(
        """SELECT a.id AS asset_id,a.uri FROM documents d JOIN document_assets a
        ON a.id=d.canonical_asset_id AND a.document_id=d.id
        WHERE d.id=%s AND d.household_id=%s AND d.deleted_at IS NULL
          AND d.original_sha256=%s AND a.sha256=%s AND a.byte_size=%s
          AND a.asset_role='original' AND a.uri=%s AND a.mime_type=%s
          AND document_is_readable(d.id,%s,%s,NULL) FOR SHARE OF a""",
        (
            document_id,
            credential.household_id,
            content.sha256,
            content.sha256,
            content.byte_size,
            uri,
            content.mime_type,
            credential.household_id,
            credential.user_id,
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise UploadUnavailable()
    return cast(dict[str, Any], row)
