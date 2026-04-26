from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.documents.access_policy import DocumentAccessContext, document_read_access_params
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
