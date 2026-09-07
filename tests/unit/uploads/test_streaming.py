from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import uuid4

import anyio
import pytest

from lib.auth.request_authority import RequestCredential
from lib.uploads.errors import UploadError
from lib.uploads.models import TransferLease, UploadCreate
from lib.uploads.policy import UploadPolicy
from lib.uploads.streaming import receive_bytes


def lease(size=32):
    identity = uuid4()
    credential = RequestCredential(
        uuid4(), uuid4(), "session", uuid4(), None, session_csrf_bound=True
    )
    metadata = UploadCreate(
        operation_id=uuid4(), client_batch_id=uuid4(), filename="a.pdf", declared_bytes=size
    )
    return TransferLease(
        uuid4(),
        identity,
        1,
        uuid4(),
        credential,
        metadata,
        "receive",
        identity,
        datetime.now(UTC) + timedelta(minutes=10),
    )


def test_empty_chunks_do_not_extend_idle_deadline(monkeypatch):
    monkeypatch.setattr("lib.uploads.streaming._flush", lambda _: None)

    async def run():
        async def chunks():
            while True:
                await anyio.sleep(0.01)
                yield b""

        policy = UploadPolicy().model_copy(update={"idle_seconds": 0.05})
        with pytest.raises(UploadError) as error:
            await receive_bytes(chunks(), io.BytesIO(), lease(), policy)
        assert error.value.code == "upload_timed_out"

    anyio.run(run)


def test_cancellation_waits_for_in_progress_filesystem_write(monkeypatch):
    entered, release, finished = Event(), Event(), Event()

    def blocked_write(stream, chunk):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("Test release deadline exceeded")
        stream.write(chunk)
        finished.set()

    monkeypatch.setattr("lib.uploads.streaming._write", blocked_write)
    closed = Event()

    async def run():
        async def worker():
            try:

                async def chunks():
                    yield b"%PDF-1.7\n"

                await receive_bytes(chunks(), io.BytesIO(), lease(), UploadPolicy())
            finally:
                assert finished.is_set(), "Cleanup ran while source writer still existed"
                closed.set()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(worker)
            assert await anyio.to_thread.run_sync(entered.wait, 5)
            tasks.cancel_scope.cancel()
            assert not closed.is_set()
            release.set()

    anyio.run(run)
    assert finished.is_set() and closed.is_set()
