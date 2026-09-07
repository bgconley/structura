from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

import lib.storage.reference_cleanup as cleanup
from lib.storage import StoredObject
from lib.uploads.cleanup import _clean_crash_publication
from lib.uploads.cleanup_repository import CleanupClaim
from lib.uploads.staging import UploadStaging
from tests.unit.uploads.test_storage import source, storage_at


@pytest.fixture
def unreferenced_database(monkeypatch):
    connection = Mock()

    @contextmanager
    def cursor():
        yield Mock()

    @contextmanager
    def database():
        yield connection

    connection.cursor = cursor
    monkeypatch.setattr(cleanup, "db_connection", database)
    monkeypatch.setattr(cleanup, "lock_content_hash", lambda *_: None)
    monkeypatch.setattr(cleanup, "_is_object_referenced", lambda *_: False)
    return connection


def stored_at(target):
    return StoredObject("canonical://sha256/" + "a" * 64 + "/original.blob", "a" * 64, 1, target)


def test_strict_unlink_syncs_parents_and_keeps_empty_directories(
    tmp_path, monkeypatch, unreferenced_database
):
    target = tmp_path / "hash" / "original.blob"
    target.parent.mkdir()
    target.write_bytes(b"a")
    observed = []

    def sync(parent):
        assert not target.exists(), "Directory sync preceded the unlink"
        observed.append(parent)

    monkeypatch.setattr(cleanup, "sync_directory", sync)
    assert (
        cleanup.cleanup_verified_unreferenced_object(stored_at(target), lambda: True) == "removed"
    )
    assert target.parent.is_dir()
    assert observed == list(target.parents)
    unreferenced_database.commit.assert_called_once()


def test_failed_unlink_sync_cannot_confirm_and_missing_retry_restores_barriers(
    tmp_path, monkeypatch, unreferenced_database
):
    target = tmp_path / "hash" / "original.blob"
    target.parent.mkdir()
    target.write_bytes(b"a")

    def fail_sync(_):
        raise OSError("Synthetic fsync failure")

    monkeypatch.setattr(cleanup, "sync_directory", fail_sync)
    with pytest.raises(OSError, match="Synthetic fsync failure"):
        cleanup.cleanup_verified_unreferenced_object(stored_at(target), lambda: True)
    assert not target.exists()
    unreferenced_database.commit.assert_not_called()
    observed = []
    monkeypatch.setattr(cleanup, "sync_directory", lambda parent: observed.append(parent))
    result = cleanup.cleanup_verified_unreferenced_object(
        stored_at(target), lambda: pytest.fail("Missing target has no deletable ownership")
    )
    assert result == "already_missing"
    assert observed == list(target.parents)


def test_missing_parent_chain_syncs_surviving_ancestors(
    tmp_path, monkeypatch, unreferenced_database
):
    target = tmp_path / "removed" / "hash" / "original.blob"
    observed = []
    real_sync = cleanup.sync_directory

    def sync(parent):
        real_sync(parent)  # Missing directories raise; surviving ones really fsync.
        observed.append(parent)

    monkeypatch.setattr(cleanup, "sync_directory", sync)
    result = cleanup.cleanup_verified_unreferenced_object(stored_at(target), lambda: False)
    assert result == "already_missing"
    assert observed == [tmp_path, *tmp_path.parents]


def test_crash_cleanup_missing_target_cannot_skip_durability_retry(
    tmp_path, monkeypatch, unreferenced_database
):
    staging = UploadStaging(storage_at(tmp_path))
    identity, content = source(staging)
    claim = CleanupClaim(uuid4(), identity, uuid4(), content.sha256, content.byte_size)
    observed = []
    real_sync = cleanup.sync_directory

    def sync(parent: Path):
        real_sync(parent)
        observed.append(parent)

    monkeypatch.setattr(cleanup, "sync_directory", sync)
    _clean_crash_publication(staging, claim)
    assert observed == [tmp_path, *tmp_path.parents]
    assert staging.path(identity).exists()
