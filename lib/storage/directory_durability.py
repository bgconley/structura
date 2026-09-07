"""Directory-entry durability within an explicit managed filesystem boundary."""

import os
from pathlib import Path

from lib.storage.service import StorageError


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure_durable_directory(path: Path, *, mode: int, boundary: Path) -> None:
    """Persist every visible ancestor, including entries another creator just made.

    A directory being visible does not prove its parent's entry was synced. Never
    infer that from exists(): concurrent preparations and retries need the same
    barrier. The configured root uses its filesystem anchor as trusted boundary;
    per-transfer paths use the already validated canonical root.
    """
    if not path.is_absolute() or not boundary.is_absolute() or not path.is_relative_to(boundary):
        raise StorageError("Managed storage directory boundary is invalid.")
    chain: list[Path] = []
    current = path
    while current != boundary:
        if len(chain) >= 256:
            raise StorageError("Managed storage directory is unavailable.")
        chain.append(current)
        current = current.parent
    if not boundary.is_dir() or boundary.is_symlink():
        raise StorageError("Managed storage directory boundary is unavailable.")
    sync_directory(boundary)
    for directory in reversed(chain):
        directory.mkdir(mode=mode, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise StorageError("Managed storage directory is unavailable.")
        sync_directory(directory)
        sync_directory(directory.parent)
