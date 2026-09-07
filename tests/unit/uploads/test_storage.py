from __future__ import annotations

import hashlib
import multiprocessing
import os
from pathlib import Path
from uuid import uuid4

import pytest

from lib.storage import ObjectStorage
from lib.storage.verified_publication import PublicationConflict, prepare_original, verify_file
from lib.uploads.errors import UploadConflict
from lib.uploads.models import VerifiedContent
from lib.uploads.staging import UploadStaging


def storage_at(root: Path) -> ObjectStorage:
    return ObjectStorage(
        canonical_root=root, derived_root=root / "derived", export_root=root / "exports"
    )


def source(staging: UploadStaging):
    identity = uuid4()
    data = b"%PDF-1.7\nimmutable source bytes\n"
    with staging.open_new(identity) as stream:
        stream.write(data)
    return identity, VerifiedContent(hashlib.sha256(data).hexdigest(), len(data), "application/pdf")


def test_publication_shares_closed_inode_and_cleanup_keeps_original(tmp_path):
    storage = storage_at(tmp_path)
    staging = UploadStaging(storage)
    identity, content = source(staging)
    with staging.lock(identity):
        prepared = prepare_original(
            storage, staging.path(identity), staging.publication_path(identity), content
        )
        stored = prepared.commit()
        assert stored.created
        assert stored.path.stat().st_ino == staging.path(identity).stat().st_ino
        staging.remove_data(identity)
        assert verify_file(stored.path, content).size == content.byte_size
        assert (staging.root / f"{identity}.lock").exists()


def test_cleanup_wins_before_publication_recreates_and_tracks_actual_created(tmp_path):
    storage = storage_at(tmp_path)
    staging = UploadStaging(storage)
    identity, content = source(staging)
    with staging.lock(identity):
        first = prepare_original(
            storage, staging.path(identity), staging.publication_path(identity), content
        )
        original = first.commit()
        prepared = prepare_original(
            storage, staging.path(identity), staging.publication_path(identity), content
        )
        assert prepared.existing_identity is not None
        original.path.unlink()  # Simulated cleanup completes before caller takes content lock.
        # Unlink changed the source inode's ctime; reprepare is required.
        with pytest.raises(PublicationConflict):
            prepared.commit()
        prepared = prepare_original(
            storage, staging.path(identity), staging.publication_path(identity), content
        )
        result = prepared.commit()
        assert result.created
        result.path.unlink()  # Simulated reference-aware rollback of actual created object.
        assert verify_file(staging.path(identity), content)


def test_existing_target_reuse_never_hashes_in_commit(tmp_path, monkeypatch):
    storage = storage_at(tmp_path)
    staging = UploadStaging(storage)
    first_id, content = source(staging)
    first = prepare_original(
        storage, staging.path(first_id), staging.publication_path(first_id), content
    )
    first.commit()
    second_id, _ = source(staging)
    prepared = prepare_original(
        storage, staging.path(second_id), staging.publication_path(second_id), content
    )
    monkeypatch.setattr(
        "lib.storage.verified_publication.verify_file", lambda *_: pytest.fail("hash in commit")
    )
    stored = prepared.commit()
    assert not stored.created


def test_same_size_target_replacement_fails_closed(tmp_path):
    storage = storage_at(tmp_path)
    staging = UploadStaging(storage)
    first_id, content = source(staging)
    first = prepare_original(
        storage, staging.path(first_id), staging.publication_path(first_id), content
    )
    first.commit()
    second_id, _ = source(staging)
    prepared = prepare_original(
        storage, staging.path(second_id), staging.publication_path(second_id), content
    )
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"x" * content.byte_size)
    replacement.replace(prepared.path)
    with pytest.raises(PublicationConflict):
        prepared.commit()


def test_hash_uses_same_open_fd_and_detects_path_swap(tmp_path, monkeypatch):
    path = tmp_path / "source"
    data = b"%PDF-1.7" + b"a" * 100
    path.write_bytes(data)
    content = VerifiedContent(hashlib.sha256(data).hexdigest(), len(data), "application/pdf")
    read = os.read
    swapped = False

    def replace_after_read(fd, count):
        nonlocal swapped
        chunk = read(fd, count)
        if not swapped:
            swapped = True
            alternate = tmp_path / "alternate"
            alternate.write_bytes(data)
            alternate.replace(path)
        return chunk

    monkeypatch.setattr(os, "read", replace_after_read)
    with pytest.raises(PublicationConflict):
        verify_file(path, content)


def _stalled_writer(root, identity, ready, release):
    staging = UploadStaging(storage_at(Path(root)))
    with staging.lock(identity):
        with staging.open_new(identity) as stream:
            stream.write(b"first bytes")
            stream.flush()
            ready.set()
            if not release.wait(10):
                raise RuntimeError("Test release deadline exceeded")
            stream.write(b"late bytes")


def test_separate_process_stalled_writer_cannot_be_cleaned_or_reopen_lock_inode(tmp_path):
    context = multiprocessing.get_context("spawn")
    ready, release = context.Event(), context.Event()
    identity = uuid4()
    process = context.Process(
        target=_stalled_writer, args=(str(tmp_path), identity, ready, release)
    )
    process.start()
    staging = UploadStaging(storage_at(tmp_path))
    try:
        assert ready.wait(10)
        inode = (staging.root / f"{identity}.lock").stat().st_ino
        with pytest.raises(UploadConflict), staging.lock(identity):
            pytest.fail("Stalled writer lock was stolen")
        assert staging.path(identity).exists()
        release.set()
        process.join(10)
        assert process.exitcode == 0
        with staging.lock(identity):
            assert staging.path(identity).read_bytes() == b"first byteslate bytes"
            staging.remove_data(identity)
        assert (staging.root / f"{identity}.lock").stat().st_ino == inode
        with staging.lock(identity):
            assert (staging.root / f"{identity}.lock").stat().st_ino == inode
    finally:
        release.set()
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join()


def test_transfer_generation_is_never_reopened_for_write(tmp_path):
    staging = UploadStaging(storage_at(tmp_path))
    identity, _ = source(staging)
    with pytest.raises(UploadConflict):
        staging.open_new(identity)


def test_within_root_symlink_parent_is_rejected_before_publication(tmp_path):
    from lib.storage.verified_publication import PublicationUnavailable

    storage = storage_at(tmp_path)
    staging = UploadStaging(storage)
    identity, content = source(staging)
    real_directory = tmp_path / "other-managed-directory"
    real_directory.mkdir()
    (tmp_path / "sha256").symlink_to(real_directory, target_is_directory=True)
    with pytest.raises(PublicationUnavailable):
        prepare_original(
            storage, staging.path(identity), staging.publication_path(identity), content
        )
    assert list(real_directory.iterdir()) == []


def test_new_directory_entries_are_synced_from_parent_to_leaf(tmp_path, monkeypatch):
    import lib.storage.directory_durability as durability

    observed = []
    monkeypatch.setattr(durability, "sync_directory", lambda path: observed.append(path))
    target = tmp_path / "a" / "b" / "c"
    durability.ensure_durable_directory(target, mode=0o700, boundary=tmp_path)
    assert observed == [
        tmp_path,
        tmp_path / "a",
        tmp_path,
        tmp_path / "a" / "b",
        tmp_path / "a",
        target,
        target.parent,
    ]


def test_prepared_publication_syncs_temp_entry_before_commit_and_leaf_after_install(
    tmp_path, monkeypatch
):
    import lib.storage.verified_publication as publication

    storage = storage_at(tmp_path)
    staging = UploadStaging(storage)
    identity, content = source(staging)
    observed = []
    monkeypatch.setattr(publication, "sync_directory", lambda path: observed.append(path))
    prepared = prepare_original(
        storage, staging.path(identity), staging.publication_path(identity), content
    )
    assert observed == [staging.root]
    prepared.commit()
    assert observed == [staging.root, prepared.path.parent]


def test_visible_unsynced_ancestor_is_synced_by_accepting_preparation(tmp_path, monkeypatch):
    import lib.storage.directory_durability as durability

    parent = tmp_path / "just-created-by-another-writer"
    parent.mkdir()  # That writer pauses before syncing the directory entry.
    observed = []
    monkeypatch.setattr(durability, "sync_directory", lambda path: observed.append(path))
    durability.ensure_durable_directory(parent / "leaf", mode=0o700, boundary=tmp_path)
    assert observed == [tmp_path, parent, tmp_path, parent / "leaf", parent]
