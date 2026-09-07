"""Bounded raw body transfer, with no SQL transaction spanning byte IO."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import BinaryIO

import anyio
from anyio.to_thread import run_sync

from lib.uploads.content import identify_content
from lib.uploads.errors import UploadError
from lib.uploads.models import TransferLease, VerifiedContent
from lib.uploads.policy import UploadPolicy
from lib.uploads.transfer_repository import renew_transfer


def _write(stream: BinaryIO, chunk: bytes) -> None:
    stream.write(chunk)


def _flush(stream: BinaryIO) -> None:
    stream.flush()
    os.fsync(stream.fileno())


async def receive_bytes(
    chunks: AsyncIterator[bytes],
    stream: BinaryIO,
    lease: TransferLease,
    policy: UploadPolicy,
) -> VerifiedContent:
    digest = hashlib.sha256()
    received = 0
    header = bytearray()
    remaining = max(0, (lease.deadline_at - datetime.now(UTC)).total_seconds())
    deadline = time.monotonic() + min(remaining, policy.absolute_seconds)
    idle_deadline = time.monotonic() + policy.idle_seconds
    next_renewal = time.monotonic() + min(10, policy.lease_seconds / 3)
    while True:
        timeout = min(deadline, idle_deadline) - time.monotonic()
        if timeout <= 0:
            raise UploadError("upload_timed_out")
        try:
            with anyio.fail_after(timeout):
                chunk = await anext(chunks)
        except StopAsyncIteration:
            break
        except TimeoutError as exc:
            raise UploadError("upload_timed_out") from exc
        if not chunk:
            continue
        received += len(chunk)
        if received > min(lease.metadata.declared_bytes, policy.max_file_bytes):
            raise UploadError("upload_too_large")
        if len(header) < 16:
            header.extend(chunk[: 16 - len(header)])
        # Non-abandoning worker: cancellation waits for this actual write to finish.
        # The caller retains source lock and reservation until stream.close completes.
        for offset in range(0, len(chunk), 1024 * 1024):
            await run_sync(_write, stream, chunk[offset : offset + 1024 * 1024])
        digest.update(chunk)
        idle_deadline = time.monotonic() + policy.idle_seconds
        if time.monotonic() >= next_renewal:
            await run_sync(renew_transfer, lease, policy)
            next_renewal = time.monotonic() + min(10, policy.lease_seconds / 3)
    await run_sync(_flush, stream)
    return identify_content(lease.metadata, bytes(header), digest.hexdigest(), received)
