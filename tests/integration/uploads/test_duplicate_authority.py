from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from lib.auth import AuthService
from lib.auth.request_authority import RequestCredential
from lib.uploads.errors import UploadUnavailable
from lib.uploads.models import UploadDecision
from lib.uploads.read_repository import read_attempt
from tests.integration.uploads.test_lifecycle import rows


def other_member(upload):
    auth = AuthService()
    owner = auth.bootstrap_admin(
        email=f"duplicate-{uuid4()}@example.com",
        password="minimum8",
        household_name=f"Other upload {uuid4()}",
    )
    rows(
        "INSERT INTO household_memberships(household_id,user_id,role) VALUES(%s,%s,'member') "
        "RETURNING user_id",
        (upload.credential.household_id, owner.user_id),
    )
    session = auth.create_password_session(
        email=owner.email, password="minimum8", household_id=upload.credential.household_id
    )
    principal = auth.resolve_session_token(session.token)
    return replace(
        upload,
        credential=RequestCredential.from_principal(principal),
        principal=principal,
        session=session,
        email=owner.email,
    )


def make_readable(upload, document_id):
    folder = rows(
        "INSERT INTO folders(name,household_id,owner_user_id,folder_kind,acl_mode) "
        "VALUES('Duplicate test folder',%s,%s,'manual','household') RETURNING id",
        (upload.credential.household_id, upload.credential.user_id),
    )[0]["id"]
    rows(
        "UPDATE documents SET primary_folder_id=%s,acl_mode='household',sensitivity='normal' "
        "WHERE id=%s RETURNING id",
        (folder, document_id),
    )
    return folder


def test_hidden_same_household_match_is_ordinary_new_acceptance_without_duplicate_metadata(upload):
    first = upload.send(upload.create())
    member = other_member(upload)
    second = member.send(member.create())
    assert second.state == "accepted" and second.duplicates == ()
    assert second.receipt.document_id != first.receipt.document_id
    row = rows(
        "SELECT duplicate_of_document_id,metadata_json FROM documents WHERE id=%s",
        (second.receipt.document_id,),
    )[0]
    assert row["duplicate_of_document_id"] is None
    assert row["metadata_json"]["upload"]["duplicateSuspect"] is False
    assert "duplicateCount" not in second.model_dump_json()


def test_revoked_exact_duplicate_choice_never_reuses_or_implicitly_creates(upload):
    first = upload.send(upload.create())
    folder = make_readable(upload, first.receipt.document_id)
    member = other_member(upload)
    held = member.send(member.create())
    assert held.state == "awaiting_duplicate_decision"
    rows("UPDATE folders SET acl_mode='private' WHERE id=%s RETURNING id", (folder,))
    with pytest.raises(UploadUnavailable):
        member.service.decide(
            held.upload_id,
            UploadDecision(
                revision=held.revision,
                decision="use_existing",
                document_id=first.receipt.document_id,
            ),
            member.credential,
        )
    current = read_attempt(held.upload_id, member.credential)
    assert current.receipt is None and current.duplicates == ()
    assert not rows("SELECT id FROM documents WHERE owner_user_id=%s", (member.credential.user_id,))


def test_reused_receipt_read_rechecks_live_document_acl(upload):
    first = upload.send(upload.create())
    folder = make_readable(upload, first.receipt.document_id)
    member = other_member(upload)
    held = member.send(member.create())
    reused = member.service.decide(
        held.upload_id,
        UploadDecision(
            revision=held.revision, decision="use_existing", document_id=first.receipt.document_id
        ),
        member.credential,
    )
    assert reused.state == "reused"
    rows("UPDATE folders SET acl_mode='private' WHERE id=%s RETURNING id", (folder,))
    with pytest.raises(UploadUnavailable):
        read_attempt(held.upload_id, member.credential)
