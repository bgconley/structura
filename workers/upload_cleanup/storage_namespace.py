"""Open a provisioned upload namespace without creating or repairing missing paths."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from lib.storage import ObjectStorage, StorageError
from lib.storage.service import StorageKind
from lib.uploads.staging import UploadStaging


class CleanupStorage(ObjectStorage):
    """Cleanup has no permission to manufacture an empty replacement namespace."""

    def __init__(self, storage: ObjectStorage) -> None:
        self.roots = dict(storage.roots)
        self.canonical_root = storage.roots["canonical"].absolute()
        self.staging_root = self.canonical_root / ".upload-attempts"
        self._identity = self._read_identity()

    def _read_identity(self) -> tuple[int, int, int, int]:
        if len(self.staging_root.parents) > 256:
            raise StorageError("Cleanup storage namespace is unavailable.")
        for path in (self.staging_root, *self.staging_root.parents):
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise StorageError("Cleanup storage namespace is unavailable.")
        canonical, staging = self.canonical_root.lstat(), self.staging_root.lstat()
        if (
            canonical.st_dev != staging.st_dev
            or staging.st_uid != os.geteuid()
            or stat.S_IMODE(staging.st_mode) != 0o700
        ):
            raise StorageError("Cleanup storage namespace is unavailable.")
        return canonical.st_dev, canonical.st_ino, staging.st_dev, staging.st_ino

    def assert_available(self) -> None:
        if self._read_identity() != self._identity:
            raise StorageError("Cleanup storage namespace changed.")

    def root_for(self, kind: StorageKind) -> Path:
        if kind != "canonical":
            raise StorageError("Cleanup storage namespace is unavailable.")
        self.assert_available()
        return self.canonical_root


class CleanupStaging(UploadStaging):
    """Use the normal stable flock/removal protocol in an existing namespace only."""

    storage: CleanupStorage

    def __init__(self, storage: ObjectStorage) -> None:
        # UploadStaging.__init__ provisions/chmods directories; maintenance must
        # never invoke it to turn missing source storage into apparent absence.
        self.storage = CleanupStorage(storage)
        self.root = self.storage.staging_root

    @contextmanager
    def lock(self, transfer_id: UUID, *, wait_seconds: float = 0) -> Iterator[None]:
        self.storage.assert_available()
        with super().lock(transfer_id, wait_seconds=wait_seconds):
            self.storage.assert_available()
            yield

    def remove_data(self, transfer_id: UUID) -> None:
        self.storage.assert_available()
        super().remove_data(transfer_id)
        self.storage.assert_available()

    def open_new(self, transfer_id: UUID) -> BinaryIO:
        raise StorageError("Cleanup cannot open upload content for writing.")
