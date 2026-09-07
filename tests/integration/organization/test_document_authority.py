from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest

from lib.auth import AuthService
from lib.auth.request_authority import RequestCredential
from lib.contracts import FolderWrite
from lib.db.connection import db_connection
from lib.organization import authority_repository, repository
from lib.organization.manual_filing import create_folder
from lib.organization.policy import OrganizationError

from ..test_completion_authorization import observe_lock_backend
from ..test_completion_session_security import wait_for_blocked
from .support import file_document, impact


def member_with_granted_folder(doc):
    auth = AuthService()
    user = auth.bootstrap_admin(
        email=f"organization-member-{uuid4()}@example.com",
        password="minimum8",
        household_name=f"Organization member {uuid4()}",
    )
    folder = create_folder(
        FolderWrite(folderKind="manual", name="Shared evidence", aclMode="custom"), doc.principal
    )
    hidden = create_folder(
        FolderWrite(folderKind="manual", name="Private evidence", aclMode="private"), doc.principal
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO household_memberships(household_id,user_id,role) VALUES(%s,%s,'member')",
            (doc.credential.household_id, user.user_id),
        )
        cur.execute(
            "INSERT INTO folder_acl(folder_id,principal_type,principal_id,permission) "
            "VALUES(%s,'user',%s,'write')",
            (folder.id, user.user_id),
        )
    file_document(doc, folderIds=[folder.id], primaryFolderId=folder.id)
    session = auth.create_password_session(
        email=user.email, password="minimum8", household_id=doc.credential.household_id
    )
    principal = auth.resolve_session_token(session.token)
    assert principal is not None
    return (
        replace(doc, principal=principal, credential=RequestCredential.from_principal(principal)),
        folder,
        hidden,
    )


@pytest.mark.parametrize("change", ["primary_folder", "primary_grant", "target_grant"])
def test_filing_checks_fresh_primary_and_target_permissions_after_real_waits(
    organization_document, monkeypatch, change
):
    doc, shared, hidden = member_with_granted_folder(organization_document)
    changes = {"title": "Must remain invisible"}
    if change == "target_grant":
        # The actor owns the document but must still have a current write grant
        # to the separately owned target folder.
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE documents SET owner_user_id=%s,primary_folder_id=NULL WHERE id=%s",
                (doc.credential.user_id, doc.document_id),
            )
            cur.execute(
                "DELETE FROM document_folder_memberships WHERE document_id=%s", (doc.document_id,)
            )
        changes.update(folderIds=[shared.id], primaryFolderId=shared.id)
    before = impact(doc)
    module, function = (
        (repository, "lock_document_for_household")
        if change == "primary_folder"
        else (authority_repository, "lock_folder_authority")
    )
    backends = observe_lock_backend(monkeypatch, module, function)
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            if change == "primary_folder":
                cur.execute(
                    "UPDATE documents SET primary_folder_id=%s WHERE id=%s",
                    (hidden.id, doc.document_id),
                )
                cur.execute(
                    "SELECT to_jsonb(d) AS doc FROM documents d WHERE id=%s", (doc.document_id,)
                )
                expected_document = cur.fetchone()["doc"]
            else:
                cur.execute(
                    "UPDATE folder_acl SET permission='read' WHERE folder_id=%s", (shared.id,)
                )
            pending = pool.submit(file_document, doc, **changes)
            try:
                # The target path calls this helper once with no current primary;
                # the same backend subsequently blocks on the requested target.
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            with pytest.raises(OrganizationError) as failure:
                pending.result(timeout=5)
    assert failure.value.status_code == (422 if change == "target_grant" else 404)
    if change == "primary_folder":
        before["fields"]["document"] = expected_document
    assert impact(doc) == before
