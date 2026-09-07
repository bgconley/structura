from __future__ import annotations

import hashlib
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from lib.db.connection import db_connection
from lib.storage import ObjectStorage
from lib.storage.reference_cleanup import cleanup_verified_unreferenced_object, lock_content_hash
from lib.storage.verified_publication import PublicationConflict, prepare_original
from lib.uploads.cleanup import clean_transfer
from lib.uploads.models import VerifiedContent
from lib.uploads.policy import UploadPolicy
from lib.uploads.service import UploadService
from lib.uploads.transfer_repository import record_verified, reserve_transfer
from tests.integration.uploads.test_lifecycle import rows
from tests.unit.uploads.test_storage import _stalled_writer


def staged(upload):
    data = b"%PDF-1.7\noriginal uploaded source"
    attempt = upload.create()
    lease = reserve_transfer(
        attempt.upload_id, attempt.revision, upload.credential, upload.service.policy
    )
    with upload.service.staging.open_new(lease.transfer_id) as stream:
        stream.write(data)
    content = VerifiedContent(hashlib.sha256(data).hexdigest(), len(data), "application/pdf")
    record_verified(lease, content)
    return lease, content


def expire(transfer_id):
    rows(
        "UPDATE upload_transfers SET lease_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE id=%s RETURNING id",
        (transfer_id,),
    )


def _crash_after_jobs(root, lease, content):
    import lib.uploads.acceptance_repository as repository

    original = repository.create_ingestion_jobs

    def crash(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(77)  # Actual process death after blob/jobs, before transaction commit.

    repository.create_ingestion_jobs = crash
    service = UploadService(ObjectStorage(canonical_root=Path(root)), UploadPolicy())
    with service.staging.lock(lease.transfer_id):
        service._finish(lease, content, None)
    os._exit(78)


def test_process_crash_after_install_before_receipt_reclaims_exact_unreferenced_links(upload):
    lease, content = staged(upload)
    root = upload.service.storage.root_for("canonical")
    process = multiprocessing.get_context("spawn").Process(
        target=_crash_after_jobs, args=(str(root), lease, content)
    )
    process.start()
    process.join(15)
    try:
        assert process.exitcode == 77
        target = (
            root
            / "sha256"
            / content.sha256[:2]
            / content.sha256[2:4]
            / content.sha256
            / "original.blob"
        )
        assert target.exists()
        assert not rows(
            "SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,)
        )
        expire(lease.transfer_id)
        assert clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
        assert not target.exists()
        assert not upload.service.staging.path(lease.transfer_id).exists()
        assert not upload.service.staging.publication_path(lease.transfer_id).exists()
        assert rows(
            "SELECT cleanup_confirmed_at FROM upload_transfers WHERE id=%s", (lease.transfer_id,)
        )[0]["cleanup_confirmed_at"]
    finally:
        if process.is_alive():
            process.terminate()
            process.join()


def test_cleanup_preserves_unreferenced_other_inode(upload):
    lease, content = staged(upload)
    prepared = prepare_original(
        upload.service.storage,
        upload.service.staging.path(lease.transfer_id),
        upload.service.staging.publication_path(lease.transfer_id),
        content,
    )
    prepared.path.write_bytes(upload.service.staging.path(lease.transfer_id).read_bytes())
    assert (
        prepared.path.stat().st_ino != upload.service.staging.path(lease.transfer_id).stat().st_ino
    )
    expire(lease.transfer_id)
    assert clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
    assert prepared.path.exists()


def test_strict_cleanup_changed_identity_preserves_file_and_reports_conflict(upload):
    lease, content = staged(upload)
    prepared = prepare_original(
        upload.service.storage,
        upload.service.staging.path(lease.transfer_id),
        upload.service.staging.publication_path(lease.transfer_id),
        content,
    )
    stored = prepared.commit()
    with pytest.raises(PublicationConflict):
        cleanup_verified_unreferenced_object(stored, lambda: False)
    assert stored.path.exists()
    reservation = rows(
        "SELECT cleanup_confirmed_at FROM upload_transfers WHERE id=%s", (lease.transfer_id,)
    )[0]
    assert reservation["cleanup_confirmed_at"] is None


def test_referenced_same_inode_is_preserved_and_reservation_can_release(upload, monkeypatch):
    # Keep successful stage links as if the process died immediately after receipt commit.
    monkeypatch.setattr(upload.service, "_abandon_and_clean", lambda *_a, **_k: None)
    accepted = upload.send(upload.create())
    transfer_id = accepted.current_transfer_id
    path = upload.service.staging.path(transfer_id)
    canonical = (
        upload.service.storage.root_for("canonical")
        / "sha256"
        / accepted.sha256[:2]
        / accepted.sha256[2:4]
        / accepted.sha256
        / "original.blob"
    )
    assert path.stat().st_ino == canonical.stat().st_ino
    expire(transfer_id)
    assert clean_transfer(upload.service.staging, transfer_id, upload.service.policy)
    assert canonical.exists() and not path.exists()
    assert rows("SELECT receipt_json FROM upload_attempts WHERE id=%s", (accepted.upload_id,))[0][
        "receipt_json"
    ]


def test_real_process_stalled_writer_stays_reserved_after_cancel_and_cleanup_claim(upload):
    from lib.uploads.operation_repository import cancel_attempt

    attempt = upload.create()
    lease = reserve_transfer(
        attempt.upload_id, attempt.revision, upload.credential, upload.service.policy
    )
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    process = context.Process(
        target=_stalled_writer,
        args=(str(upload.service.storage.root_for("canonical")), lease.transfer_id, ready, release),
    )
    process.start()
    try:
        assert ready.wait(10)
        cancel_attempt(attempt.upload_id, upload.credential)
        assert not clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
        record = rows("SELECT * FROM upload_transfers WHERE id=%s", (lease.transfer_id,))[0]
        assert record["cleanup_confirmed_at"] is None and record["io_stopped_at"] is None
        release.set()
        process.join(10)
        assert process.exitcode == 0
        rows(
            "UPDATE upload_transfers SET cleanup_expires_at=clock_timestamp()-interval '1 second' "
            "WHERE id=%s RETURNING id",
            (lease.transfer_id,),
        )
        assert clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
        assert not upload.service.staging.path(lease.transfer_id).exists()
    finally:
        release.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join()


def test_cleanup_rechecks_exact_identity_after_waiting_for_content_lock(upload, monkeypatch):
    import lib.storage.reference_cleanup as cleanup_repository

    lease, content = staged(upload)
    prepared = prepare_original(
        upload.service.storage,
        upload.service.staging.path(lease.transfer_id),
        upload.service.staging.publication_path(lease.transfer_id),
        content,
    )
    stored = prepared.commit()
    expire(lease.transfer_id)
    waiting = Event()
    original = cleanup_repository.lock_content_hash

    def observed(cur, digest):
        waiting.set()
        original(cur, digest)

    monkeypatch.setattr(cleanup_repository, "lock_content_hash", observed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with db_connection() as conn, conn.cursor() as cur:
            lock_content_hash(cur, content.sha256)
            future = pool.submit(
                clean_transfer, upload.service.staging, lease.transfer_id, upload.service.policy
            )
            assert waiting.wait(10)
            replacement = stored.path.parent / "controlled-replacement"
            replacement.write_bytes(b"x" * content.byte_size)
            replacement.replace(stored.path)
            conn.commit()
        with pytest.raises(PublicationConflict):
            future.result(timeout=10)
    assert stored.path.read_bytes() == b"x" * content.byte_size
    assert upload.service.staging.path(lease.transfer_id).exists()
    assert (
        rows("SELECT cleanup_confirmed_at FROM upload_transfers WHERE id=%s", (lease.transfer_id,))[
            0
        ]["cleanup_confirmed_at"]
        is None
    )


def test_duplicate_decision_locks_exact_held_source_while_expiry_cleanup_waits(upload, monkeypatch):
    import lib.uploads.service as service_module
    from lib.uploads.errors import UploadConflict
    from lib.uploads.models import UploadDecision
    from lib.uploads.read_repository import read_attempt

    first = upload.send(upload.create())
    held = upload.send(upload.create())
    source_id = held.current_transfer_id
    entered, proceed = Event(), Event()
    original = service_module.prepare_original

    def paused(storage, source, publication, content):
        prepared = original(storage, source, publication, content)
        entered.set()
        assert proceed.wait(10)
        return prepared

    monkeypatch.setattr(service_module, "prepare_original", paused)
    command = UploadDecision(
        revision=held.revision, decision="use_existing", document_id=first.receipt.document_id
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(upload.service.decide, held.upload_id, command, upload.credential)
        try:
            assert entered.wait(10)
            rows(
                "UPDATE upload_transfers SET held_until=clock_timestamp()-interval '1 second' "
                "WHERE id=%s RETURNING id",
                (source_id,),
            )
            # Claim can revoke, but must not remove the source currently used by decision.
            assert not clean_transfer(upload.service.staging, source_id, upload.service.policy)
            assert upload.service.staging.path(source_id).exists()
            assert (
                rows("SELECT cleanup_confirmed_at FROM upload_transfers WHERE id=%s", (source_id,))[
                    0
                ]["cleanup_confirmed_at"]
                is None
            )
        finally:
            proceed.set()
        with pytest.raises(UploadConflict):
            future.result(timeout=10)
    assert read_attempt(held.upload_id, upload.credential).state == "expired"
    assert (
        len(rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,)))
        == 1
    )
