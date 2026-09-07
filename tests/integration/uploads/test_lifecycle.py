from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from psycopg.errors import RaiseException

from lib.auth import AuthService
from lib.auth.authorization_policy import AuthorizationError
from lib.auth.request_authority import RequestCredential
from lib.db.connection import db_connection
from lib.uploads.cleanup import clean_transfer
from lib.uploads.errors import UploadCapacity, UploadConflict
from lib.uploads.models import UploadDecision
from lib.uploads.operation_repository import cancel_attempt, create_attempt
from lib.uploads.policy import UploadPolicy
from lib.uploads.read_repository import read_attempt
from lib.uploads.transfer_repository import renew_transfer, reserve_transfer


def rows(sql, params=()):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_lost_response_same_operation_and_verified_replay_return_one_receipt(upload):
    metadata = upload.command()
    attempt = create_attempt(metadata, upload.credential, upload.service.policy)
    accepted = upload.send(attempt)
    recovered = create_attempt(metadata, upload.credential, upload.service.policy)
    replayed = upload.send(recovered)
    assert accepted.receipt == recovered.receipt == replayed.receipt
    assert accepted.state == "accepted"
    assert (
        len(rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,)))
        == 1
    )
    assert (
        len(
            rows(
                "SELECT id FROM pipeline_jobs WHERE document_id=%s", (accepted.receipt.document_id,)
            )
        )
        == 4
    )
    assert not list(upload.service.staging.root.glob("*.data"))
    assert not list(upload.service.staging.root.glob("*.publish"))


def test_changed_metadata_or_accepted_replay_bytes_conflict(upload):
    metadata = upload.command()
    attempt = create_attempt(metadata, upload.credential, upload.service.policy)
    accepted = upload.send(attempt)
    with pytest.raises(UploadConflict):
        create_attempt(
            metadata.model_copy(update={"title": "changed"}),
            upload.credential,
            upload.service.policy,
        )
    changed = b"%PDF-1.7\ndifferent uploaded source"
    assert len(changed) == metadata.declared_bytes
    with pytest.raises(UploadConflict):
        upload.send(accepted, changed)
    assert read_attempt(attempt.upload_id, upload.credential).receipt == accepted.receipt
    assert (
        len(rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,)))
        == 1
    )


def test_exact_duplicate_is_held_then_explicitly_reused_without_jobs(upload):
    accepted = upload.send(upload.create())
    held = upload.send(upload.create())
    assert held.state == "awaiting_duplicate_decision"
    assert [candidate.document_id for candidate in held.duplicates] == [
        accepted.receipt.document_id
    ]
    result = upload.service.decide(
        held.upload_id,
        UploadDecision(
            revision=held.revision,
            decision="use_existing",
            document_id=accepted.receipt.document_id,
        ),
        upload.credential,
    )
    assert result.state == "reused"
    assert result.receipt.document_id == accepted.receipt.document_id
    assert result.receipt.asset_id == accepted.receipt.asset_id
    assert result.receipt.job_id is None and result.receipt.batch_id is None
    assert (
        len(rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,)))
        == 1
    )


def test_keep_separate_then_cancel_preserves_independent_receipt(upload):
    first = upload.send(upload.create())
    held = upload.send(upload.create())
    second = upload.service.decide(
        held.upload_id,
        UploadDecision(revision=held.revision, decision="keep_separate"),
        upload.credential,
    )
    assert second.receipt.document_id != first.receipt.document_id
    cancelled = cancel_attempt(held.upload_id, upload.credential)
    assert cancelled.receipt == second.receipt
    assert cancelled.state == "accepted"
    rows_after = rows(
        "SELECT duplicate_of_document_id FROM documents WHERE id=%s", (second.receipt.document_id,)
    )
    assert rows_after[0]["duplicate_of_document_id"] is None


def test_cancelled_operation_key_never_recreates_original(upload):
    metadata = upload.command()
    attempt = create_attempt(metadata, upload.credential, upload.service.policy)
    cancelled = cancel_attempt(attempt.upload_id, upload.credential)
    recovered = create_attempt(metadata, upload.credential, upload.service.policy)
    assert recovered.revision == cancelled.revision and recovered.state == "cancelled"
    with pytest.raises(UploadConflict):
        upload.send(recovered)
    assert not rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,))


def test_cancel_does_not_release_reserved_bytes_until_cleanup(upload):
    attempt = upload.create()
    lease = reserve_transfer(
        attempt.upload_id, attempt.revision, upload.credential, upload.service.policy
    )
    cancel_attempt(attempt.upload_id, upload.credential)
    reserved = rows("SELECT * FROM upload_transfers WHERE id=%s", (lease.transfer_id,))[0]
    assert reserved["cleanup_confirmed_at"] is None
    assert reserved["io_stopped_at"] is None
    with pytest.raises(UploadConflict):
        renew_transfer(lease, upload.service.policy)
    assert clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
    assert rows(
        "SELECT cleanup_confirmed_at FROM upload_transfers WHERE id=%s", (lease.transfer_id,)
    )[0]["cleanup_confirmed_at"]


def test_capacity_counts_expired_and_held_reservations_until_cleaned(upload):
    policy = UploadPolicy(actor_active_limit=1, global_active_limit=1)
    first, second = upload.create(), upload.create()
    lease = reserve_transfer(first.upload_id, first.revision, upload.credential, policy)
    rows(
        "UPDATE upload_transfers SET lease_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE id=%s RETURNING id",
        (lease.transfer_id,),
    )
    with pytest.raises(UploadCapacity):
        reserve_transfer(second.upload_id, second.revision, upload.credential, policy)
    assert clean_transfer(upload.service.staging, lease.transfer_id, policy)
    assert reserve_transfer(second.upload_id, second.revision, upload.credential, policy)


def test_captured_session_revocation_and_explicit_new_generation(upload):
    attempt = upload.create()
    old = reserve_transfer(
        attempt.upload_id, attempt.revision, upload.credential, upload.service.policy
    )
    rows(
        "UPDATE sessions SET revoked_at=clock_timestamp() WHERE id=%s RETURNING id",
        (upload.credential.session_id,),
    )
    with pytest.raises(AuthorizationError):
        renew_transfer(old, upload.service.policy)
    session = AuthService().create_password_session(email=upload.email, password="minimum8")
    principal = AuthService().resolve_session_token(session.token)
    credential = RequestCredential.from_principal(principal)
    current = read_attempt(attempt.upload_id, credential)
    new = reserve_transfer(
        attempt.upload_id,
        current.revision,
        credential,
        upload.service.policy,
        replace_transfer_id=old.transfer_id,
    )
    assert new.generation == old.generation + 1
    assert new.source_transfer_id != old.source_transfer_id
    forged = replace(old, credential=credential)
    with pytest.raises(UploadConflict):
        renew_transfer(forged, upload.service.policy)


def test_immutable_sql_identity_and_receipt_tombstones(upload):
    attempt = upload.send(upload.create())
    for statement in [
        "UPDATE upload_attempts SET metadata_json='{}'::jsonb WHERE id=%s",
        "UPDATE upload_attempts SET receipt_json='{}'::jsonb WHERE id=%s",
        "DELETE FROM upload_attempts WHERE id=%s",
    ]:
        with pytest.raises(RaiseException):
            rows(statement + " RETURNING id", (attempt.upload_id,))
    assert read_attempt(attempt.upload_id, upload.credential).receipt == attempt.receipt


def test_stale_revision_and_arbitrary_duplicate_id_never_choose_another_document(upload):
    first = upload.send(upload.create())
    held = upload.send(upload.create())
    with pytest.raises(UploadConflict):
        upload.service.decide(
            held.upload_id,
            UploadDecision(revision=uuid4(), decision="keep_separate"),
            upload.credential,
        )
    from lib.uploads.errors import UploadUnavailable

    with pytest.raises(UploadUnavailable):
        upload.service.decide(
            held.upload_id,
            UploadDecision(revision=held.revision, decision="use_existing", document_id=uuid4()),
            upload.credential,
        )
    current = read_attempt(held.upload_id, upload.credential)
    assert current.state == "awaiting_duplicate_decision"
    reused = upload.service.decide(
        current.upload_id,
        UploadDecision(
            revision=current.revision,
            decision="use_existing",
            document_id=first.receipt.document_id,
        ),
        upload.credential,
    )
    assert reused.receipt.document_id == first.receipt.document_id


def test_unstarted_registration_expiry_recovers_capacity_without_reusing_operation_keys(upload):
    from lib.uploads.cleanup import clean_expired_uploads

    policy = UploadPolicy(queue_reference_limit=2)
    first_command, second_command = upload.command(), upload.command()
    first = create_attempt(first_command, upload.credential, policy)
    create_attempt(second_command, upload.credential, policy)
    with pytest.raises(UploadCapacity):
        create_attempt(upload.command(), upload.credential, policy)
    rows(
        "UPDATE upload_attempts SET inactive_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE actor_user_id=%s RETURNING id",
        (upload.credential.user_id,),
    )
    clean_expired_uploads(upload.service.staging, policy)
    assert create_attempt(upload.command(), upload.credential, policy).state == "awaiting_content"
    old = create_attempt(first_command, upload.credential, policy)
    assert old.upload_id == first.upload_id and old.state == "expired"
    with pytest.raises(UploadConflict):
        upload.send(old)
    assert not rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,))


def test_inactive_deadline_cannot_expire_an_active_or_held_generation(upload):
    from lib.uploads.inactive_repository import expire_inactive_attempts

    active = upload.create()
    lease = reserve_transfer(
        active.upload_id, active.revision, upload.credential, upload.service.policy
    )
    rows(
        "UPDATE upload_attempts SET inactive_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE id=%s RETURNING id",
        (active.upload_id,),
    )
    expire_inactive_attempts()
    assert read_attempt(active.upload_id, upload.credential).state == "receiving"
    cancel_attempt(active.upload_id, upload.credential)
    clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
    upload.send(upload.create())
    held = upload.send(upload.create())
    rows(
        "UPDATE upload_attempts SET inactive_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE id=%s RETURNING id",
        (held.upload_id,),
    )
    expire_inactive_attempts()
    assert read_attempt(held.upload_id, upload.credential).state == "awaiting_duplicate_decision"


def test_failed_cleaned_retry_slot_expires_and_cannot_start_with_old_revision(upload):
    from lib.uploads.inactive_repository import expire_inactive_attempts
    from lib.uploads.transfer_repository import abandon_transfer

    attempt = upload.create()
    lease = reserve_transfer(
        attempt.upload_id, attempt.revision, upload.credential, upload.service.policy
    )
    abandon_transfer(lease, upload.service.policy)
    clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
    retry = read_attempt(attempt.upload_id, upload.credential)
    assert retry.state == "awaiting_content"
    rows(
        "UPDATE upload_attempts SET inactive_expires_at=clock_timestamp() WHERE id=%s RETURNING id",
        (attempt.upload_id,),
    )
    expire_inactive_attempts()
    assert read_attempt(attempt.upload_id, upload.credential).state == "expired"
    with pytest.raises(UploadConflict):
        reserve_transfer(
            attempt.upload_id, retry.revision, upload.credential, upload.service.policy
        )


def test_put_checks_inactive_deadline_even_before_maintenance_runs(upload):
    attempt = upload.create()
    rows(
        "UPDATE upload_attempts SET inactive_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE id=%s RETURNING id",
        (attempt.upload_id,),
    )
    with pytest.raises(UploadConflict):
        reserve_transfer(
            attempt.upload_id, attempt.revision, upload.credential, upload.service.policy
        )
    assert not rows("SELECT id FROM upload_transfers WHERE upload_id=%s", (attempt.upload_id,))
