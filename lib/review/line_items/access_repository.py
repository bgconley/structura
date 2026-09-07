"""Line review resource locks follow the shared live request credential prefix."""

from typing import Any
from uuid import UUID

from lib.auth.request_authority import RequestCredential
from lib.auth.request_authority_repository import assert_request_authority, lock_request_authority
from lib.review.errors import ReviewRepositoryError


def lock_line_review(cur: Any, document_id: UUID, credential: RequestCredential) -> None:
    lock_request_authority(cur, credential, "documents:review")
    cur.execute("SELECT id FROM documents WHERE id=%s FOR UPDATE", (document_id,))
    if cur.fetchone() is None:
        raise ReviewRepositoryError("Document not found.")
    cur.execute("SELECT primary_folder_id FROM documents WHERE id=%s", (document_id,))
    folder = cur.fetchone()["primary_folder_id"]
    if folder is not None:
        cur.execute("SELECT id FROM folders WHERE id=%s FOR SHARE", (folder,))
        cur.fetchone()
        cur.execute(
            "SELECT id FROM folder_acl WHERE folder_id=%s AND ((principal_type='user' "
            "AND principal_id=%s)"
            "OR (principal_type='household' AND principal_id=%s)) ORDER BY id FOR SHARE",
            (folder, credential.user_id, credential.household_id),
        )
        cur.fetchall()
    assert_line_review(cur, document_id, credential)


def assert_line_review(cur: Any, document_id: UUID, credential: RequestCredential) -> None:
    assert_request_authority(cur, credential, "documents:review")
    cur.execute(
        "SELECT document_is_writable(id,%s,%s,NULL) AS allowed FROM documents "
        "WHERE id=%s AND deleted_at IS NULL",
        (credential.household_id, credential.user_id, document_id),
    )
    row = cur.fetchone()
    if row is None or not row["allowed"]:
        raise ReviewRepositoryError("Document not found.")
