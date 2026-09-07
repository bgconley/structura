from __future__ import annotations

import pytest

from lib.evidence.blob_commit import prepare_render_commit
from tests.unit.evidence.test_media import source_fixture


def test_verified_staging_survives_cleanup_and_recreates_exact_destination(tmp_path):
    storage, stored, asset, data = source_fixture(tmp_path)
    with prepare_render_commit(asset, storage) as prepared:
        stored.path.unlink()
        prepared.commit_under_content_lock()
        assert prepared.committed.created
        assert stored.path.read_bytes() == data
        staged_path = prepared.staged.temp_path
    assert not staged_path.exists()


def test_failed_transaction_cleans_actual_recreated_object_after_context_unwinds(
    tmp_path, monkeypatch
):
    storage, stored, asset, _ = source_fixture(tmp_path)
    cleaned = []

    def cleanup(value):
        assert rolled_back
        cleaned.append(value)
        if value.created:
            value.path.unlink()

    monkeypatch.setattr("lib.evidence.blob_commit.cleanup_unreferenced_stored_object", cleanup)
    rolled_back = False
    with pytest.raises(RuntimeError):
        with prepare_render_commit(asset, storage) as prepared:
            stored.path.unlink()
            prepared.commit_under_content_lock()
            assert prepared.committed.created
            rolled_back = True
            raise RuntimeError("Controlled final fence denial after rollback")
    assert len(cleaned) == 1 and not stored.path.exists()
    assert not prepared.staged.temp_path.exists()


def test_existing_object_and_committed_shared_bytes_are_not_destructively_replaced(tmp_path):
    storage, stored, asset, data = source_fixture(tmp_path)
    inode = stored.path.stat().st_ino
    with prepare_render_commit(asset, storage) as prepared:
        prepared.commit_under_content_lock()
        assert not prepared.committed.created
    assert stored.path.stat().st_ino == inode and stored.path.read_bytes() == data
