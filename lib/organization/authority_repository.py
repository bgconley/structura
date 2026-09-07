"""Transaction-held credentials and fresh document/folder authority for filing."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID

from lib.auth import AuthPrincipal
from lib.auth.authorization_policy import AuthorizationError, require_action
from lib.auth.request_authority import RequestCredential
from lib.auth.request_authority_repository import assert_request_authority, lock_request_authority
from lib.documents.access_policy import DocumentAccessContext, document_write_access_params
from lib.organization.policy import organization_error


@contextmanager
def organization_mutation(
    cur: Any, principal: AuthPrincipal, *, catalog: bool = False
) -> Iterator[None]:
    """Enter before domain locks; the enclosing caller commits immediately after exit.

    Only synchronous entry points use this credential boundary. The advisory key
    reserves one household organization namespace; catalog changes exclude filing.
    Future topology writers must enroll all their reference-admission paths too.
    """
    try:
        require_action(principal, "documents:write")
        credential = RequestCredential.from_principal(principal)
        lock_request_authority(cur, credential, "documents:write")
        if catalog:
            cur.execute(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended('structura.organization:' || %s, 0))",
                (str(credential.household_id),),
            )
        else:
            cur.execute(
                "SELECT pg_advisory_xact_lock_shared("
                "hashtextextended('structura.organization:' || %s, 0))",
                (str(credential.household_id),),
            )
        assert_request_authority(cur, credential, "documents:write")
        yield
        assert_request_authority(cur, credential, "documents:write")
    except AuthorizationError as exc:
        raise organization_error(403, "Permission denied") from exc


def lock_folder_authority(
    cur: Any, folder_ids: list[UUID], *, household_id: UUID, user_id: UUID
) -> None:
    ordered = sorted(set(folder_ids))
    if not ordered:
        return
    cur.execute("SELECT id FROM folders WHERE id=ANY(%s::uuid[]) ORDER BY id FOR SHARE", (ordered,))
    cur.fetchall()
    cur.execute(
        "SELECT id FROM folder_acl WHERE folder_id=ANY(%s::uuid[]) AND "
        "((principal_type='user' AND principal_id=%s) OR "
        "(principal_type='household' AND principal_id=%s)) ORDER BY id FOR SHARE",
        (ordered, user_id, household_id),
    )
    cur.fetchall()


def lock_writable_document(
    cur: Any, document_id: UUID, access: DocumentAccessContext
) -> dict[str, Any] | None:
    # Keep locking and authorization in separate statements: a concurrent refile
    # can change the primary folder while this request waits for the document.
    cur.execute("SELECT id FROM documents WHERE id=%s FOR UPDATE", (document_id,))
    if cur.fetchone() is None:
        return None
    cur.execute("SELECT primary_folder_id FROM documents WHERE id=%s", (document_id,))
    folder_id = cur.fetchone()["primary_folder_id"]
    lock_folder_authority(
        cur,
        [folder_id] if folder_id else [],
        household_id=access.household_id,
        user_id=access.user_id,
    )
    cur.execute(
        "SELECT id,primary_folder_id FROM documents d WHERE id=%s AND deleted_at IS NULL "
        "AND document_is_writable(d.id,%s,%s,%s)",
        (document_id, *document_write_access_params(access)),
    )
    return cast(dict[str, Any] | None, cur.fetchone())
