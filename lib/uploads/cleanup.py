"""One bounded cleanup pass; busy writers stay charged, including expired leases."""

import math
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from uuid import UUID

import psycopg

from lib.storage import StorageError, StoredObject
from lib.storage.reference_cleanup import cleanup_verified_unreferenced_object
from lib.storage.service import object_uri
from lib.storage.verified_publication import FileIdentity, PublicationConflict
from lib.uploads.cleanup_repository import (
    CleanupClaim,
    claim_cleanup,
    cleanup_candidates,
    finish_cleanup,
)
from lib.uploads.errors import UploadConflict
from lib.uploads.inactive_repository import expire_inactive_attempts
from lib.uploads.policy import UploadPolicy
from lib.uploads.staging import UploadStaging


def clean_transfer(staging: UploadStaging, transfer_id: UUID, policy: UploadPolicy) -> bool:
    claim = claim_cleanup(transfer_id, policy)
    if claim is None:
        return False
    # Claim committed first; no SQL locks while acquiring the stable OS lock.
    try:
        with staging.lock(transfer_id):
            _clean_crash_publication(staging, claim)
            staging.remove_data(transfer_id)
            finish_cleanup(claim)
            return True
    except UploadConflict:
        return False


def clean_expired_uploads(staging: UploadStaging, policy: UploadPolicy, *, limit: int = 100) -> int:
    expire_inactive_attempts(limit=limit)
    return sum(
        clean_transfer(staging, identity, policy) for identity in cleanup_candidates(limit=limit)
    )


@dataclass(frozen=True)
class CleanupSweep:
    inactive_expired: int = 0
    selected: int = 0
    attempted: int = 0
    cleaned: int = 0
    deferred: int = 0
    failed: int = 0
    interrupted: bool = False
    error_codes: tuple[str, ...] = ()


def sweep_expired_uploads(
    staging: UploadStaging,
    policy: UploadPolicy,
    *,
    limit: int = 100,
    budget_seconds: float = 20,
    should_stop: Callable[[], bool] = lambda: False,
    progress: Callable[[], None] = lambda: None,
    before_claim: Callable[[], None] = lambda: None,
) -> CleanupSweep:
    """A supervised sweep isolates item failures without dropping reservations.

    The time budget only stops NEW work. A running filesystem operation retains
    its source lock until it returns; no thread/IO is abandoned on timeout.
    """
    if not 1 <= limit <= 100 or not math.isfinite(budget_seconds) or budget_seconds <= 0:
        raise ValueError("Upload cleanup sweep limits are invalid.")
    if should_stop():
        return CleanupSweep(interrupted=True)
    deadline = time.monotonic() + budget_seconds
    progress()
    expired = expire_inactive_attempts(limit=limit)
    candidates = cleanup_candidates(limit=limit)
    attempted = cleaned = deferred = 0
    errors = []
    interrupted = False
    for identity in candidates:
        progress()
        if should_stop() or time.monotonic() >= deadline:
            interrupted = True
            break
        attempted += 1
        try:
            before_claim()
            if clean_transfer(staging, identity, policy):
                cleaned += 1
            else:
                deferred += 1
        except PublicationConflict:
            errors.append("cleanup_source_conflict")
        except (OSError, StorageError):
            errors.append("cleanup_storage_unavailable")
        except psycopg.Error:
            errors.append("cleanup_database_unavailable")
            break  # Do not spend one connection timeout per remaining item.
        finally:
            progress()
    return CleanupSweep(
        expired,
        len(candidates),
        attempted,
        cleaned,
        deferred,
        len(errors),
        interrupted,
        tuple(errors),
    )


def clean_locked_transfer(staging: UploadStaging, transfer_id: UUID, policy: UploadPolicy) -> bool:
    """Writer already holds this exact stable lock through its commit/cleanup."""
    claim = claim_cleanup(transfer_id, policy)
    if claim is None:
        return False
    _clean_crash_publication(staging, claim)
    staging.remove_data(transfer_id)
    finish_cleanup(claim)
    return True


def _clean_crash_publication(staging: UploadStaging, claim: CleanupClaim) -> None:
    """Prove this transfer created the link; existing shared bytes are never inferred."""
    if claim.content_sha256 is None or claim.content_bytes is None:
        return
    uri = object_uri(kind="canonical", sha256=claim.content_sha256, filename="original.blob")
    target = (
        staging.storage.root_for("canonical")
        / "sha256"
        / claim.content_sha256[:2]
        / claim.content_sha256[2:4]
        / claim.content_sha256
        / "original.blob"
    )
    for parent in (target, *target.parents):
        if parent.is_symlink():
            return
        if parent == staging.storage.root_for("canonical"):
            break
    try:
        target_info = target.lstat()
    except FileNotFoundError:
        # A previous cleanup may have unlinked before its durability barrier
        # failed. Confirm missing under the content lock and sync ancestors;
        # an intervening new link has no proved ownership and must be retained.
        cleanup_verified_unreferenced_object(
            StoredObject(uri, claim.content_sha256, claim.content_bytes, target, created=True),
            lambda: False,
        )
        return
    if not stat.S_ISREG(target_info.st_mode) or target_info.st_size != claim.content_bytes:
        return
    for candidate in (staging.path(claim.transfer_id), staging.publication_path(claim.transfer_id)):
        try:
            source = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(source.st_mode) and (source.st_dev, source.st_ino) == (
            target_info.st_dev,
            target_info.st_ino,
        ):
            expected_target = FileIdentity.read(target_info)
            expected_source = FileIdentity.read(source)

            cleanup_verified_unreferenced_object(
                StoredObject(uri, claim.content_sha256, claim.content_bytes, target, created=True),
                partial(_same_identity, target, expected_target, candidate, expected_source),
            )
            return


def _same_identity(
    target: Path, expected_target: FileIdentity, source: Path, expected_source: FileIdentity
) -> bool:
    try:
        return (
            FileIdentity.read(target.lstat()) == expected_target
            and FileIdentity.read(source.lstat()) == expected_source
        )
    except FileNotFoundError:
        return False
