"""Publish a closed upload inode without hashing under a database lock.

The caller keeps the source generation's stable OS lock from verification through
commit/cleanup. Participating canonical writers hold lock_content_hash for commit;
cleanup shares it. Arbitrary external filesystem writers are outside that promise.
Existing targets are hashed through an open FD outside SQL and reused only if
path/FD identity, size and nanosecond modification/change times still match under
that lock. A changed/missing preparation is retried outside SQL, never trusted.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lib.storage.directory_durability import ensure_durable_directory, sync_directory
from lib.storage.service import ObjectStorage, StorageError, StoredObject, object_uri


class VerifiedFileContent(Protocol):
    @property
    def sha256(self) -> str: ...

    @property
    def byte_size(self) -> int: ...


class PublicationConflict(StorageError):
    """The prepared file identity changed; prepare again outside the transaction."""


class PublicationUnavailable(StorageError):
    """The filesystem cannot uphold the required bounded publication contract."""


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int

    @classmethod
    def read(cls, value: os.stat_result) -> FileIdentity:
        if not stat.S_ISREG(value.st_mode):
            raise PublicationUnavailable("Original publication is unavailable.")
        return cls(value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def verify_file(path: Path, content: VerifiedFileContent) -> FileIdentity:
    """Bounded open-FD hash, with before/after FD and non-followed path comparison."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = FileIdentity.read(os.fstat(fd))
        if before != FileIdentity.read(path.lstat()) or before.size != content.byte_size:
            raise PublicationConflict("Prepared original identity changed.")
        digest = hashlib.sha256()
        remaining = content.byte_size
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise PublicationConflict("Prepared original identity changed.")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1) or digest.hexdigest() != content.sha256:
            raise PublicationConflict("Prepared original identity changed.")
        if before != FileIdentity.read(os.fstat(fd)) or before != FileIdentity.read(path.lstat()):
            raise PublicationConflict("Prepared original identity changed.")
        return before
    finally:
        os.close(fd)


@dataclass
class PreparedOriginal:
    path: Path
    source_path: Path
    publication_path: Path
    source_identity: FileIdentity
    existing_identity: FileIdentity | None
    content: VerifiedFileContent
    uri: str
    stored: StoredObject | None = None

    def commit(self) -> StoredObject:
        """Caller holds document then content-hash SQL locks; no full-file read."""
        # Creating the temporary hardlink changes ctime; preparation freezes after it.
        if FileIdentity.read(self.source_path.lstat()) != self.source_identity:
            raise PublicationConflict("Prepared original identity changed.")
        if FileIdentity.read(self.publication_path.lstat()) != self.source_identity:
            raise PublicationConflict("Prepared original identity changed.")
        try:
            current = FileIdentity.read(self.path.lstat())
        except FileNotFoundError:
            current = None
        if current is not None:
            if self.existing_identity != current:
                raise PublicationConflict("Prepared original identity changed.")
            created = False
        else:
            # Atomic link install cannot overwrite an object created by another writer.
            # The temporary publication link remains for crash/rollback cleanup.
            os.link(self.publication_path, self.path, follow_symlinks=False)
            created = True
            self.stored = StoredObject(
                self.uri, self.content.sha256, self.content.byte_size, self.path, created=True
            )
            sync_directory(self.path.parent)
        self.stored = StoredObject(
            self.uri, self.content.sha256, self.content.byte_size, self.path, created=created
        )
        return self.stored


def prepare_original(
    storage: ObjectStorage,
    source: Path,
    publication: Path,
    content: VerifiedFileContent,
) -> PreparedOriginal:
    """Source lock held; all hashing/preparation precedes the acceptance transaction."""
    # Canonical originals are shared with the existing worker group; staging parent is0700.
    # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
    os.chmod(source, 0o660, follow_symlinks=False)  # nosec B103
    verify_file(source, content)
    uri = object_uri(kind="canonical", sha256=content.sha256, filename="original.blob")
    root = storage.root_for("canonical")
    target = (
        root
        / "sha256"
        / content.sha256[:2]
        / content.sha256[2:4]
        / content.sha256
        / "original.blob"
    )
    # The managed root/parents must not contain symlinks, including within-root links.
    for path in (source, publication.parent, target, *target.parents):
        if path.is_symlink():
            raise PublicationUnavailable("Original publication is unavailable.")
        if path == root:
            break
    ensure_durable_directory(target.parent, mode=0o2770, boundary=root)
    publication.unlink(missing_ok=True)
    os.link(source, publication, follow_symlinks=False)
    sync_directory(publication.parent)
    source_identity = verify_file(source, content)
    if FileIdentity.read(publication.lstat()) != source_identity:
        raise PublicationConflict("Prepared original identity changed.")
    try:
        existing = verify_file(target, content)
    except FileNotFoundError:
        existing = None
    return PreparedOriginal(target, source, publication, source_identity, existing, content, uri)
