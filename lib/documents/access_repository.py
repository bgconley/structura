"""Persisted authorization checks shared by document mutations and derived job reads."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal
from uuid import UUID

from lib.auth import AuthPrincipal
from lib.auth.authorization_policy import permits_action
from lib.db.connection import db_connection
from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
    document_review_access_params,
    document_write_access_params,
)


def document_is_writable(cur: Any, document_id: UUID, access: DocumentAccessContext) -> bool:
    return lock_writable_documents(cur, [document_id], access)


def lock_writable_documents(
    cur: Any,
    document_ids: Sequence[UUID],
    access: DocumentAccessContext,
    *,
    action: Literal["write", "review"] = "write",
) -> bool:
    """Lock a stable document set, then authorize using a fresh statement snapshot.

    A permission predicate in the locking SELECT can be evaluated before waiting
    for a concurrent refile. Keep the lock and authority queries separate.
    """
    ordered_ids = sorted(set(document_ids))
    if not ordered_ids:
        return True
    cur.execute(
        "SELECT id FROM documents WHERE id = ANY(%s::uuid[]) ORDER BY id FOR UPDATE",
        (ordered_ids,),
    )
    if len(cur.fetchall()) != len(ordered_ids):
        return False
    params = (
        document_review_access_params(access)
        if action == "review"
        else document_write_access_params(access)
    )
    cur.execute(
        """SELECT bool_and(document_is_writable(id, %s, %s, %s)) AS allowed
        FROM unnest(%s::uuid[]) AS selected(id)""",
        (*params, ordered_ids),
    )
    row = cur.fetchone()
    return bool(row and row["allowed"])


def job_is_readable(job_id: UUID, principal: AuthPrincipal) -> bool:
    if not principal.household_id:
        return False
    access = DocumentAccessContext(
        household_id=principal.household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
        api_token_id=principal.api_token_id,
        scopes=principal.scopes,
    )
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.document_id,
                       document_is_readable(j.document_id, %s, %s, %s) AS readable
                FROM pipeline_jobs j
                JOIN household_memberships hm
                  ON hm.household_id = j.household_id AND hm.user_id = %s
                JOIN users u ON u.id = hm.user_id AND NOT u.is_disabled
                WHERE j.id = %s AND j.household_id = %s
                  AND (j.document_id IS NOT NULL OR hm.role IN ('owner', 'admin'))
                """,
                (
                    *document_read_access_params(access),
                    principal.user_id,
                    job_id,
                    principal.household_id,
                ),
            )
            row = cur.fetchone()
    if not row:
        return False
    if row["document_id"] is None:
        return permits_action(principal, "jobs:admin")
    return permits_action(principal, "documents:read") and bool(row["readable"])
