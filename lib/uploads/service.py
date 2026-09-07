"""Upload orchestration: outside-SQL IO, exact lease admission and safe cleanup."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import ExitStack
from functools import partial
from uuid import UUID

import anyio
from anyio.to_thread import run_sync

from lib.auth.request_authority import RequestCredential
from lib.storage import ObjectStorage, StorageError, cleanup_unreferenced_stored_object
from lib.storage.verified_publication import PreparedOriginal, PublicationConflict, prepare_original
from lib.uploads.acceptance_repository import finish_transfer
from lib.uploads.cleanup import clean_locked_transfer, clean_transfer
from lib.uploads.errors import UploadConflict, UploadError, UploadStorageUnavailable
from lib.uploads.models import TransferLease, UploadAttempt, UploadDecision, VerifiedContent
from lib.uploads.policy import UploadPolicy
from lib.uploads.staging import UploadStaging
from lib.uploads.streaming import receive_bytes
from lib.uploads.transfer_repository import (
    abandon_transfer,
    held_content,
    record_verified,
    reject_transfer,
    renew_transfer,
    reserve_transfer,
    revoke_source,
)


class UploadService:
    def __init__(
        self, storage: ObjectStorage | None = None, policy: UploadPolicy | None = None
    ) -> None:
        self.storage = storage or ObjectStorage()
        self.policy = policy or UploadPolicy()
        self.staging = UploadStaging(self.storage)

    async def receive(
        self,
        upload_id: UUID,
        revision: UUID,
        credential: RequestCredential,
        chunks: AsyncIterator[bytes],
        *,
        replace_transfer_id: UUID | None = None,
        declared_length: int | None = None,
    ) -> UploadAttempt:
        lease = await run_sync(
            partial(
                reserve_transfer,
                upload_id,
                revision,
                credential,
                self.policy,
                replace_transfer_id=replace_transfer_id,
            )
        )
        held = False
        locks = ExitStack()
        source_locked = False
        try:
            if declared_length is not None and declared_length != lease.metadata.declared_bytes:
                raise UploadError("upload_size_mismatch")
            # OS lock acquisition is bounded and happens after the admission TX closed.
            with anyio.CancelScope(shield=True):
                await run_sync(
                    locks.enter_context,
                    self.staging.lock(
                        lease.source_transfer_id, wait_seconds=self.policy.lock_wait_seconds
                    ),
                )
                source_locked = True
            await run_sync(renew_transfer, lease, self.policy)
            # run_sync shields this open until its returned FD has an owner.
            stream = await run_sync(self.staging.open_new, lease.transfer_id)
            try:
                content = await receive_bytes(chunks, stream, lease, self.policy)
            finally:
                with anyio.CancelScope(shield=True):
                    await run_sync(stream.close)
            await run_sync(self.staging.sync_received_entry)
            await run_sync(record_verified, lease, content)
            result = await run_sync(self._finish, lease, content, None)
            held = result.state == "awaiting_duplicate_decision"
            return result
        except UploadError as exc:
            with anyio.CancelScope(shield=True):
                await run_sync(reject_transfer, lease, exc.code)
            raise
        except (OSError, StorageError) as exc:
            raise UploadStorageUnavailable() from exc
        finally:
            # Cancellation cannot abandon ownership cleanup while file IO continues.
            # A held duplicate remains reserved; its source lock is reacquired for decision.
            try:
                if not held:
                    with anyio.CancelScope(shield=True):
                        await run_sync(
                            partial(self._abandon_and_clean, lease, source_locked=source_locked)
                        )
            finally:
                with anyio.CancelScope(shield=True):
                    await run_sync(locks.close)

    def decide(
        self, upload_id: UUID, command: UploadDecision, credential: RequestCredential
    ) -> UploadAttempt:
        lease = reserve_transfer(
            upload_id, command.revision, credential, self.policy, decision=True
        )
        completed = False
        locks = ExitStack()
        source_locked = False
        try:
            # This exact source-transfer lock prevents expiry cleanup racing reuse.
            locks.enter_context(
                self.staging.lock(
                    lease.source_transfer_id, wait_seconds=self.policy.lock_wait_seconds
                )
            )
            source_locked = True
            renew_transfer(lease, self.policy)
            content = held_content(lease)
            result = self._finish(lease, content, command)
            completed = True
            return result
        except (OSError, StorageError) as exc:
            raise UploadStorageUnavailable() from exc
        finally:
            try:
                self._abandon_and_clean(lease)
                if completed and source_locked:
                    revoke_source(lease)
                    clean_locked_transfer(self.staging, lease.source_transfer_id, self.policy)
            finally:
                locks.close()

    def _finish(
        self, lease: TransferLease, content: VerifiedContent, command: UploadDecision | None
    ) -> UploadAttempt:
        for retry in range(2):
            prepared: PreparedOriginal | None = None
            committed = False
            try:
                prepared = prepare_original(
                    self.storage,
                    self.staging.path(lease.source_transfer_id),
                    self.staging.publication_path(lease.source_transfer_id),
                    content,
                )
                renew_transfer(lease, self.policy, require_open=False)
                result = finish_transfer(lease, prepared, content, self.policy, decision=command)
                committed = True
                return result
            except PublicationConflict:
                if retry:
                    raise UploadConflict() from None
            finally:
                # Callback's actual created flag survives a failed transaction.
                if prepared and not committed:
                    cleanup_unreferenced_stored_object(prepared.stored)
        raise UploadConflict()

    def _abandon_and_clean(self, lease: TransferLease, *, source_locked: bool = False) -> None:
        abandon_transfer(lease, self.policy)
        cleanup = clean_locked_transfer if source_locked else clean_transfer
        cleanup(self.staging, lease.transfer_id, self.policy)
