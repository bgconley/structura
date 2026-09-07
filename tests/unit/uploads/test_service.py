from __future__ import annotations

from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from threading import Event, get_ident
from uuid import uuid4

import anyio
import httpx
import pytest
from fastapi import FastAPI

from apps.api.structura_api import routes_uploads
from lib.auth.models import AuthPrincipal
from lib.uploads.errors import UploadConflict
from lib.uploads.models import UploadAttempt
from lib.uploads.policy import UploadPolicy
from lib.uploads.service import UploadService
from tests.unit.uploads.test_storage import storage_at
from tests.unit.uploads.test_streaming import lease


def configure_service(tmp_path, monkeypatch):
    service = UploadService(storage_at(tmp_path), UploadPolicy(lock_wait_seconds=1))
    admitted = lease()
    monkeypatch.setattr("lib.uploads.service.reserve_transfer", lambda *_a, **_k: admitted)
    monkeypatch.setattr("lib.uploads.service.renew_transfer", lambda *_a: None)
    monkeypatch.setattr("lib.uploads.service.reject_transfer", lambda *_a: None)
    return service, admitted


def test_busy_source_flock_does_not_block_event_loop(tmp_path, monkeypatch):
    service, admitted = configure_service(tmp_path, monkeypatch)
    entered, released = Event(), Event()
    real_lock = service.staging.lock

    @contextmanager
    def observed_lock(*args, **kwargs):
        entered.set()
        with real_lock(*args, **kwargs):
            assert released.is_set(), "Writer proceeded before the existing owner released"
            yield

    monkeypatch.setattr(service.staging, "lock", observed_lock)
    monkeypatch.setattr(service, "_abandon_and_clean", lambda *_a, **_k: None)
    with ExitStack() as held:
        held.enter_context(real_lock(admitted.source_transfer_id))

        async def run():
            async def receive():
                async def chunks():
                    raise UploadConflict()
                    yield b"never"

                with pytest.raises(UploadConflict):
                    await service.receive(
                        admitted.upload_id, uuid4(), admitted.credential, chunks()
                    )

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(receive)
                assert await anyio.to_thread.run_sync(entered.wait, 5)
                # This scheduled work must run while the real flock is still held.
                await anyio.sleep(0.02)
                released.set()
                held.close()

        anyio.run(run)
    with real_lock(admitted.source_transfer_id):
        pass  # The receiver did not retain the stable lock.


def test_cancellation_during_flock_acquisition_waits_and_cleans_owned_lease(tmp_path, monkeypatch):
    service, admitted = configure_service(tmp_path, monkeypatch)
    entered, acquired, cleaned, finished = Event(), Event(), Event(), Event()
    real_lock = service.staging.lock
    reserved = {admitted.transfer_id}

    @contextmanager
    def observed_lock(*args, **kwargs):
        entered.set()
        with real_lock(*args, **kwargs):
            acquired.set()
            yield

    def cleanup(current, *, source_locked=False):
        assert current == admitted and source_locked and acquired.is_set()
        with pytest.raises(UploadConflict), real_lock(admitted.source_transfer_id):
            pytest.fail("Cleanup lost its source lock before reservation accounting")
        assert not service.staging.path(admitted.transfer_id).exists()
        reserved.remove(current.transfer_id)
        cleaned.set()

    monkeypatch.setattr(service.staging, "lock", observed_lock)
    monkeypatch.setattr(service, "_abandon_and_clean", cleanup)
    monkeypatch.setattr(
        service.staging, "open_new", lambda *_: pytest.fail("Cancelled transfer opened a writer")
    )
    with ExitStack() as held:
        held.enter_context(real_lock(admitted.source_transfer_id))

        async def run():
            async def receive():
                async def chunks():
                    pytest.fail("Cancelled transfer consumed body")
                    yield b"never"

                try:
                    await service.receive(
                        admitted.upload_id, uuid4(), admitted.credential, chunks()
                    )
                finally:
                    finished.set()

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(receive)
                assert await anyio.to_thread.run_sync(entered.wait, 5)
                tasks.cancel_scope.cancel()
                assert reserved and not finished.is_set() and not cleaned.is_set()
                held.close()

        anyio.run(run)
    assert acquired.is_set() and cleaned.is_set() and finished.is_set() and not reserved
    with real_lock(admitted.source_transfer_id):
        pass


@pytest.mark.parametrize("kind", ["content", "decision"])
def test_route_staging_initialization_does_not_block_unrelated_request(monkeypatch, kind):
    entered, released = Event(), Event()
    loop_thread = get_ident()
    identity, revision = uuid4(), uuid4()
    principal = AuthPrincipal(
        uuid4(),
        uuid4(),
        "person@example.test",
        "Person",
        "password",
        session_id=uuid4(),
        csrf_token_hash="already-validated-by-dependency",
    )
    observation = UploadAttempt(
        upload_id=identity,
        operation_id=uuid4(),
        client_batch_id=uuid4(),
        revision=revision,
        state="awaiting_content",
        filename="source.pdf",
        declared_bytes=32,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class DelayedService:
        def __init__(self, **_kwargs):
            assert get_ident() != loop_thread, "Staging mkdir/fsync ran on ASGI event loop"
            entered.set()
            if not released.wait(5):
                raise RuntimeError("Initialization release deadline exceeded")

        async def receive(self, *_args, **_kwargs):
            return observation

        def decide(self, *_args, **_kwargs):
            assert get_ident() != loop_thread
            return observation

    monkeypatch.setattr(routes_uploads, "UploadService", DelayedService)
    app = FastAPI()
    app.include_router(routes_uploads.router)
    app.dependency_overrides[routes_uploads.require_document_write] = lambda: principal

    @app.get("/progress")
    async def progress():
        assert entered.is_set() and not released.is_set()
        released.set()
        return {"progress": True}

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def upload():
                if kind == "content":
                    response = await client.put(
                        f"/api/v1/uploads/{identity}/content",
                        content=b"",
                        headers={"If-Match": str(revision)},
                    )
                else:
                    response = await client.post(
                        f"/api/v1/uploads/{identity}/decision",
                        json={"revision": str(revision), "decision": "keep_separate"},
                    )
                assert response.status_code == 200

            async with anyio.create_task_group() as tasks:
                tasks.start_soon(upload)
                assert await anyio.to_thread.run_sync(entered.wait, 5)
                response = await client.get("/progress")
                assert response.json() == {"progress": True}

    anyio.run(run)


def test_cancellation_during_file_open_closes_fd_before_accounting(tmp_path, monkeypatch):
    service, admitted = configure_service(tmp_path, monkeypatch)
    entered, released, cleaned = Event(), Event(), Event()
    loop_thread = get_ident()
    opened = []
    real_open = service.staging.open_new

    def delayed_open(identity):
        assert get_ident() != loop_thread
        stream = real_open(identity)
        opened.append(stream)
        entered.set()
        if not released.wait(5):
            raise RuntimeError("File open release deadline exceeded")
        return stream

    def cleanup(current, *, source_locked=False):
        assert current == admitted and source_locked
        assert len(opened) == 1 and opened[0].closed
        service.staging.remove_data(current.transfer_id)
        cleaned.set()

    monkeypatch.setattr(service.staging, "open_new", delayed_open)
    monkeypatch.setattr(service, "_abandon_and_clean", cleanup)

    async def run():
        async def receive():
            async def chunks():
                await anyio.sleep(0)  # First cancellation checkpoint after the shielded open.
                pytest.fail("Cancelled transfer read content")
                yield b"never"

            await service.receive(admitted.upload_id, uuid4(), admitted.credential, chunks())

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(receive)
            assert await anyio.to_thread.run_sync(entered.wait, 5)
            tasks.cancel_scope.cancel()
            assert not cleaned.is_set() and not opened[0].closed
            released.set()

    anyio.run(run)
    assert cleaned.is_set() and not service.staging.path(admitted.transfer_id).exists()
    with service.staging.lock(admitted.source_transfer_id):
        pass
