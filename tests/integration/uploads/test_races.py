from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from lib.uploads.errors import UploadConflict
from lib.uploads.operation_repository import cancel_attempt
from lib.uploads.read_repository import read_attempt
from tests.integration.uploads.test_lifecycle import rows


def test_independent_connections_same_hash_admission_create_once_and_hold_second(upload):
    attempts = [upload.create(), upload.create()]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(upload.send, attempts))
    assert sorted(outcome.state for outcome in outcomes) == [
        "accepted",
        "awaiting_duplicate_decision",
    ]
    assert (
        len(rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,)))
        == 1
    )


def test_cancellation_wins_while_raw_body_is_still_arriving(upload):
    import anyio

    attempt = upload.create()
    received, proceed = Event(), Event()

    async def body():
        yield b"%PDF-1.7\n"
        received.set()
        assert await anyio.to_thread.run_sync(proceed.wait, 10)
        yield b"original uploaded source"

    def stream():
        async def run():
            return await upload.service.receive(
                attempt.upload_id, attempt.revision, upload.credential, body()
            )

        return anyio.run(run)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(stream)
        try:
            assert received.wait(10)
            cancelled = cancel_attempt(attempt.upload_id, upload.credential)
            assert cancelled.state == "cancelled"
            reservation = rows(
                "SELECT * FROM upload_transfers WHERE upload_id=%s", (attempt.upload_id,)
            )[0]
            assert reservation["cleanup_confirmed_at"] is None
        finally:
            proceed.set()
        with pytest.raises(UploadConflict):
            future.result(timeout=10)
    assert not rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,))
    assert not list(upload.service.staging.root.glob("*.data"))


def test_acceptance_wins_and_waiting_cancel_returns_exact_receipt(upload, monkeypatch):
    import lib.uploads.acceptance_repository as repository

    attempt = upload.create()
    entered, proceed, cancelling = Event(), Event(), Event()
    original = repository._new_receipt

    def paused(*args, **kwargs):
        receipt = original(*args, **kwargs)
        entered.set()
        assert proceed.wait(10)
        return receipt

    monkeypatch.setattr(repository, "_new_receipt", paused)

    def cancel():
        cancelling.set()
        return cancel_attempt(attempt.upload_id, upload.credential)

    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted_future = pool.submit(upload.send, attempt)
        try:
            assert entered.wait(10)
            cancelled_future = pool.submit(cancel)
            assert cancelling.wait(10)
        finally:
            proceed.set()
        accepted = accepted_future.result(timeout=10)
        cancelled = cancelled_future.result(timeout=10)
    assert cancelled.state == "accepted"
    assert cancelled.receipt == accepted.receipt


def test_post_job_exception_rolls_back_document_receipt_and_actual_created_blob(
    upload, monkeypatch
):
    import lib.uploads.acceptance_repository as repository

    original = repository.create_ingestion_jobs

    def fail_after_jobs(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("controlled post-job rollback")

    monkeypatch.setattr(repository, "create_ingestion_jobs", fail_after_jobs)
    attempt = upload.create()
    with pytest.raises(RuntimeError, match="controlled post-job rollback"):
        upload.send(attempt)
    assert not rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,))
    assert not list(upload.service.storage.root_for("canonical").glob("sha256/*/*/*/original.blob"))
    assert not list(upload.service.staging.root.glob("*.data"))
    assert read_attempt(attempt.upload_id, upload.credential).receipt is None
    monkeypatch.setattr(repository, "create_ingestion_jobs", original)
    assert upload.send(read_attempt(attempt.upload_id, upload.credential)).state == "accepted"
