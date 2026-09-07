"""Private transfer files and stable cross-process lock inodes, outside SQL.

Lock files are permanent. Never unlink a lock inode: a waiting process may hold
that inode while a new process opens its replacement. Only generated UUID paths
are used. A generation's data is opened once with O_EXCL, never truncated/reused.
"""

from __future__ import annotations

import fcntl
import os
import stat
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from lib.storage import ObjectStorage
from lib.storage.directory_durability import ensure_durable_directory, sync_directory
from lib.uploads.errors import UploadConflict, UploadStorageUnavailable


class UploadStaging:
    def __init__(self, storage: ObjectStorage) -> None:
        self.storage = storage
        configured_root = storage.roots["canonical"].resolve()
        ensure_durable_directory(
            configured_root, mode=0o2770, boundary=Path(configured_root.anchor)
        )
        self.root = storage.root_for("canonical") / ".upload-attempts"
        ensure_durable_directory(self.root, mode=0o700, boundary=storage.root_for("canonical"))
        if self.root.is_symlink() or not self.root.is_dir():
            raise UploadStorageUnavailable()
        # Owner-only directory access is required; no group/world source disclosure.
        # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
        os.chmod(self.root, 0o700)

    def path(self, transfer_id: UUID) -> Path:
        return self.root / f"{transfer_id}.data"

    def publication_path(self, transfer_id: UUID) -> Path:
        return self.root / f"{transfer_id}.publish"

    @contextmanager
    def lock(self, transfer_id: UUID, *, wait_seconds: float = 0) -> Iterator[None]:
        lock_path = self.root / f"{transfer_id}.lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        acquired = False
        try:
            sync_directory(self.root)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise UploadStorageUnavailable()
            deadline = time.monotonic() + wait_seconds
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise UploadConflict() from exc
                    time.sleep(min(0.01, max(0, deadline - time.monotonic())))
            yield
        finally:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def open_new(self, transfer_id: UUID) -> BinaryIO:
        try:
            fd = os.open(
                self.path(transfer_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
        except FileExistsError as exc:
            raise UploadConflict() from exc
        return os.fdopen(fd, "wb")

    def remove_data(self, transfer_id: UUID) -> None:
        # Caller holds the stable transfer lock and has a committed cleanup claim.
        self.publication_path(transfer_id).unlink(missing_ok=True)
        self.path(transfer_id).unlink(missing_ok=True)
        sync_directory(self.root)

    def sync_received_entry(self) -> None:
        """The data FD was closed/fsynced; persist its directory before SQL verification."""
        sync_directory(self.root)
