"""DB plus separate-process cleanup/restart evidence, with no inference services."""

from __future__ import annotations

import multiprocessing
import signal
import subprocess
import sys
from uuid import uuid4

import pytest

import lib.uploads.cleanup as cleanup
from lib.storage.verified_publication import PublicationConflict, prepare_original
from lib.uploads.cleanup_repository import cleanup_candidates
from lib.uploads.staging import UploadStaging
from lib.uploads.transfer_repository import reserve_transfer
from tests.integration.uploads.cleanup_process import (
    PipeBarrier,
    barrier_worker,
    run_once,
    runtime_environment,
    stalled_writer,
    transfer_record,
    wait_for,
    wait_for_claim_expiry,
)
from tests.integration.uploads.test_cleanup import expire, staged
from tests.integration.uploads.test_lifecycle import rows


@pytest.mark.parametrize("stage", ["after_claim", "after_unlink"])
def test_sigkill_worker_restart_preserves_reservation_until_durable_confirmation(
    upload, tmp_path, stage
):
    environment = runtime_environment(upload, tmp_path)
    lease, content = staged(upload)
    with upload.service.staging.lock(lease.transfer_id):
        installed = prepare_original(
            upload.service.storage,
            upload.service.staging.path(lease.transfer_id),
            upload.service.staging.publication_path(lease.transfer_id),
            content,
        ).commit()  # A process died after install, before its DB acceptance receipt.
    lock = upload.service.staging.root / f"{lease.transfer_id}.lock"
    inode = lock.stat().st_ino
    expire(lease.transfer_id)
    before = transfer_record(lease.transfer_id)
    context = multiprocessing.get_context("spawn")
    ready, release = PipeBarrier(context), PipeBarrier(context)
    process = context.Process(
        target=barrier_worker,
        args=(environment, stage, lease.transfer_id, ready, release),
    )
    process.start()
    try:
        assert ready.wait(15)
        process.kill()
        process.join(10)
        assert process.exitcode == -signal.SIGKILL
        interrupted = transfer_record(lease.transfer_id)
        assert interrupted["cleanup_confirmed_at"] is None
        assert interrupted["reserved_bytes"] == before["reserved_bytes"] > 0
        assert interrupted["io_stopped_at"] == before["io_stopped_at"]
        assert upload.service.staging.path(lease.transfer_id).exists() == (stage == "after_claim")
        assert installed.path.exists() == (stage == "after_claim")
        wait_for_claim_expiry(lease.transfer_id)
        run_once(environment)
        completed = transfer_record(lease.transfer_id)
        assert completed["cleanup_confirmed_at"] is not None
        assert not upload.service.staging.path(lease.transfer_id).exists()
        assert not installed.path.exists()
        assert not upload.service.staging.publication_path(lease.transfer_id).exists()
        run_once(environment)  # Terminal cleanup is not replayed or re-created.
        assert (
            transfer_record(lease.transfer_id)["cleanup_confirmed_at"]
            == completed["cleanup_confirmed_at"]
        )
        assert lock.stat().st_ino == inode
        assert not rows(
            "SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,)
        )
    finally:
        release.set()
        if process.is_alive():
            process.kill()
            process.join(10)
        ready.close()
        release.close()


def test_stalled_writer_is_skipped_then_process_death_allows_restart_cleanup(upload, tmp_path):
    environment = runtime_environment(upload, tmp_path)
    attempt = upload.create()
    lease = reserve_transfer(
        attempt.upload_id, attempt.revision, upload.credential, upload.service.policy
    )
    context = multiprocessing.get_context("spawn")
    ready, release = PipeBarrier(context), PipeBarrier(context)
    process = context.Process(
        target=stalled_writer,
        args=(str(upload.service.storage.root_for("canonical")), lease.transfer_id, ready, release),
    )
    process.start()
    try:
        assert ready.wait(15)
        expire(lease.transfer_id)
        lock = upload.service.staging.root / f"{lease.transfer_id}.lock"
        inode = lock.stat().st_ino
        run_once(environment)
        record = transfer_record(lease.transfer_id)
        assert record["cleanup_confirmed_at"] is None and record["io_stopped_at"] is None
        assert record["reserved_bytes"] > 0
        assert upload.service.staging.path(lease.transfer_id).read_bytes() == b"first bytes"
        process.kill()
        process.join(10)
        wait_for_claim_expiry(lease.transfer_id)
        run_once(environment)
        assert transfer_record(lease.transfer_id)["cleanup_confirmed_at"] is not None
        assert not upload.service.staging.path(lease.transfer_id).exists()
        assert lock.stat().st_ino == inode
    finally:
        release.set()
        if process.is_alive():
            process.kill()
            process.join(10)
        ready.close()
        release.close()


def test_sigterm_finishes_owned_item_without_claiming_the_next(upload, tmp_path):
    environment = runtime_environment(upload, tmp_path)
    # Give the active cleanup transaction ample ownership for the graceful-stop assertion.
    environment["STRUCTURA_UPLOAD_CLEANUP_LEASE_SECONDS"] = "30"
    first, _ = staged(upload)
    expire(first.transfer_id)
    second, _ = staged(upload)
    expire(second.transfer_id)
    context = multiprocessing.get_context("spawn")
    ready, release = PipeBarrier(context), PipeBarrier(context)
    process = context.Process(
        target=barrier_worker,
        args=(environment, "after_unlink", first.transfer_id, ready, release),
    )
    process.start()
    try:
        assert ready.wait(15)
        process.terminate()  # Actual SIGTERM executes the worker's signal handler.
        process.join(0.15)
        assert process.is_alive()
        assert transfer_record(first.transfer_id)["cleanup_confirmed_at"] is None
        release.set()
        process.join(10)
        assert process.exitcode == 0
        assert transfer_record(first.transfer_id)["cleanup_confirmed_at"] is not None
        assert transfer_record(second.transfer_id)["cleanup_token"] is None
        run_once(environment)
        assert transfer_record(second.transfer_id)["cleanup_confirmed_at"] is not None
    finally:
        release.set()
        if process.is_alive():
            process.kill()
            process.join(10)
        ready.close()
        release.close()


def test_supervised_loop_sweeps_immediately_and_exits_during_interval_wait(upload, tmp_path):
    environment = runtime_environment(upload, tmp_path)
    environment["STRUCTURA_UPLOAD_CLEANUP_INTERVAL_SECONDS"] = "15"
    environment["STRUCTURA_UPLOAD_CLEANUP_STALE_SECONDS"] = "90"
    lease, _ = staged(upload)
    expire(lease.transfer_id)
    process = subprocess.Popen(
        [sys.executable, "-m", "workers.upload_cleanup.worker"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for(lambda: transfer_record(lease.transfer_id)["cleanup_confirmed_at"])
        process.terminate()
        output, errors = process.communicate(timeout=5)
        assert process.returncode == 0
        assert "upload_cleanup_sweep" in errors
        assert "Traceback" not in output + errors
        assert "original.pdf" not in output + errors
        assert (
            rows(
                "SELECT status FROM service_health_snapshots "
                "WHERE service_name='worker-upload-cleanup' ORDER BY checked_at DESC LIMIT 1"
            )[0]["status"]
            == "ok"
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_worker_expires_inactive_and_held_attempts_preserving_accepted_receipt(upload, tmp_path):
    environment = runtime_environment(upload, tmp_path)
    data = f"%PDF-1.7\nworker held duplicate {uuid4()}".encode()
    accepted = upload.send(upload.create(data), data)
    held = upload.send(upload.create(data), data)
    assert held.state == "awaiting_duplicate_decision"
    inactive = upload.create()
    rows(
        "UPDATE upload_attempts SET inactive_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE id=%s RETURNING id",
        (inactive.upload_id,),
    )
    rows(
        "UPDATE upload_transfers SET held_until=clock_timestamp()-interval '1 second' "
        "WHERE id=%s RETURNING id",
        (held.current_transfer_id,),
    )
    before = rows("SELECT receipt_json FROM upload_attempts WHERE id=%s", (accepted.upload_id,))[0]
    run_once(environment)
    assert rows(
        "SELECT state FROM upload_attempts WHERE id=ANY(%s) ORDER BY id",
        ([inactive.upload_id, held.upload_id],),
    ) == [{"state": "expired"}, {"state": "expired"}]
    assert transfer_record(held.current_transfer_id)["cleanup_confirmed_at"] is not None
    assert (
        rows("SELECT receipt_json FROM upload_attempts WHERE id=%s", (accepted.upload_id,))[0]
        == before
    )
    canonical = (
        upload.service.storage.root_for("canonical")
        / "sha256"
        / accepted.sha256[:2]
        / accepted.sha256[2:4]
        / accepted.sha256
        / "original.blob"
    )
    assert canonical.read_bytes() == data
    assert not upload.service.staging.path(held.current_transfer_id).exists()


@pytest.mark.parametrize("missing", ["canonical", "staging"])
def test_process_with_missing_namespace_cannot_confirm_cleanup_or_recreate_paths(
    upload, tmp_path, missing
):
    environment = runtime_environment(upload, tmp_path)
    lease, _ = staged(upload)
    expire(lease.transfer_id)
    canonical = upload.service.storage.roots["canonical"]
    target = canonical if missing == "canonical" else upload.service.staging.root
    retained = tmp_path / "retained-namespace"
    target.rename(retained)
    before = transfer_record(lease.transfer_id)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "workers.upload_cleanup.worker", "--once"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 1
        assert "cleanup_storage_unavailable" in result.stderr
        assert not target.exists()
        record = transfer_record(lease.transfer_id)
        assert record["cleanup_confirmed_at"] is None and record["cleanup_token"] is None
        assert record["reserved_bytes"] == before["reserved_bytes"] > 0
        source = retained / ".upload-attempts" if missing == "canonical" else retained
        assert (source / f"{lease.transfer_id}.data").exists()
    finally:
        retained.rename(target)
    run_once(environment)
    assert transfer_record(lease.transfer_id)["cleanup_confirmed_at"] is not None


@pytest.mark.parametrize("replaced", ["canonical", "staging"])
def test_running_worker_rejects_replacement_namespace_after_claim_wait(upload, tmp_path, replaced):
    environment = runtime_environment(upload, tmp_path)
    lease, _ = staged(upload)
    expire(lease.transfer_id)
    target = (
        upload.service.storage.roots["canonical"]
        if replaced == "canonical"
        else upload.service.staging.root
    )
    retained = tmp_path / "retained-namespace"
    context = multiprocessing.get_context("spawn")
    ready, release = PipeBarrier(context), PipeBarrier(context)
    process = context.Process(
        target=barrier_worker,
        args=(environment, "after_claim", lease.transfer_id, ready, release),
    )
    process.start()
    try:
        assert ready.wait(15)
        target.rename(retained)
        UploadStaging(upload.service.storage)
        release.set()
        process.join(10)
        assert process.exitcode == 1
        record = transfer_record(lease.transfer_id)
        assert record["cleanup_confirmed_at"] is None and record["reserved_bytes"] > 0
        source = retained / ".upload-attempts" if replaced == "canonical" else retained
        assert (source / f"{lease.transfer_id}.data").exists()
        assert not upload.service.staging.path(lease.transfer_id).exists()
    finally:
        release.set()
        if process.is_alive():
            process.kill()
            process.join(10)
        ready.close()
        release.close()
        if retained.exists():
            if target.exists():
                target.rename(tmp_path / "unused-replacement")
            retained.rename(target)
    wait_for_claim_expiry(lease.transfer_id)
    run_once(environment)
    assert transfer_record(lease.transfer_id)["cleanup_confirmed_at"] is not None


def test_poisoned_prefix_rotates_after_claim_expiry_without_releasing_its_bytes(
    upload, monkeypatch
):
    leases = []
    for _ in range(4):
        lease, _ = staged(upload)
        expire(lease.transfer_id)
        leases.append(lease)
    poison = {lease.transfer_id for lease in leases[:2]}
    original = cleanup.clean_transfer

    def fail_after_committed_claim(staging, identity, policy):
        if identity in poison:
            assert cleanup.claim_cleanup(identity, policy) is not None
            raise PublicationConflict("test injected source identity mismatch")
        return original(staging, identity, policy)

    monkeypatch.setattr(cleanup, "clean_transfer", fail_after_committed_claim)
    first = cleanup.sweep_expired_uploads(upload.service.staging, upload.service.policy, limit=2)
    assert first.failed == 2 and first.cleaned == 0
    assert set(cleanup_candidates(limit=2)) == {lease.transfer_id for lease in leases[2:]}
    # Simulate a long worker backoff, so exclusion of LIVE claims alone cannot pass.
    rows(
        "UPDATE upload_transfers SET cleanup_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE id=ANY(%s) RETURNING id",
        (list(poison),),
    )
    second = cleanup.sweep_expired_uploads(upload.service.staging, upload.service.policy, limit=2)
    assert second.cleaned == 2 and second.failed == 0
    for identity in poison:
        record = transfer_record(identity)
        assert record["cleanup_confirmed_at"] is None and record["reserved_bytes"] > 0
        assert upload.service.staging.path(identity).exists()
