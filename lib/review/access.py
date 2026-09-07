from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.auth.authorization_policy import scopes_permit_action
from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
    document_review_access_params,
)
from lib.review.errors import ReviewRepositoryError


def assert_readable(cur: Any, document_id: UUID, access: DocumentAccessContext) -> None:
    cur.execute(
        """
        SELECT document_is_readable(id, %s, %s, %s) AS readable
        FROM documents
        WHERE id = %s
          AND deleted_at IS NULL
        """,
        (*document_read_access_params(access), document_id),
    )
    row = cur.fetchone()
    if not row or not row["readable"]:
        raise ReviewRepositoryError("Document not found.")


def assert_writable(cur: Any, document_id: UUID, access: DocumentAccessContext) -> None:
    # Match the candidate-publication prefix before canonical/actor/job FK writes.
    # SHARE, rather than KEY SHARE, serializes privilege revocation as well as deletion.
    cur.execute("SELECT id FROM households WHERE id=%s FOR KEY SHARE", (access.household_id,))
    if cur.fetchone() is None:
        raise ReviewRepositoryError("Document not found.")
    cur.execute("SELECT id FROM users WHERE id=%s FOR SHARE", (access.user_id,))
    if cur.fetchone() is None:
        raise ReviewRepositoryError("Document not found.")
    cur.execute(
        "SELECT user_id FROM household_memberships WHERE household_id=%s AND user_id=%s FOR SHARE",
        (access.household_id, access.user_id),
    )
    if cur.fetchone() is None:
        raise ReviewRepositoryError("Document not found.")
    if access.api_token_id:
        cur.execute("SELECT id FROM api_tokens WHERE id=%s FOR SHARE", (access.api_token_id,))
        if cur.fetchone() is None:
            raise ReviewRepositoryError("Document not found.")
    cur.execute("SELECT id FROM documents WHERE id=%s FOR UPDATE", (document_id,))
    if cur.fetchone() is None:
        raise ReviewRepositoryError("Document not found.")
    cur.execute("SELECT primary_folder_id FROM documents WHERE id=%s", (document_id,))
    folder_id = cur.fetchone()["primary_folder_id"]
    if folder_id:
        cur.execute("SELECT id FROM folders WHERE id=%s FOR SHARE", (folder_id,))
        cur.fetchone()
        cur.execute(
            "SELECT id FROM folder_acl WHERE folder_id=%s AND "
            "((principal_type='user' AND principal_id=%s) OR "
            "(principal_type='household' AND principal_id=%s)) ORDER BY id FOR SHARE",
            (folder_id, access.user_id, access.household_id),
        )
        cur.fetchall()
    if access.api_token_id:
        cur.execute(
            "SELECT scopes FROM api_tokens WHERE id=%s AND user_id=%s AND household_id=%s "
            "AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>clock_timestamp())",
            (access.api_token_id, access.user_id, access.household_id),
        )
        token = cur.fetchone()
        if token is None or not scopes_permit_action(tuple(token["scopes"]), "documents:review"):
            raise ReviewRepositoryError("Document not found.")
    cur.execute(
        """
        SELECT document_is_writable(id, %s, %s, %s) AS writable
        FROM documents
        WHERE id = %s AND deleted_at IS NULL
        """,
        (*document_review_access_params(access), document_id),
    )
    row = cur.fetchone()
    if not row or not row["writable"]:
        raise ReviewRepositoryError("Document not found.")
