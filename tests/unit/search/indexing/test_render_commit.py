from __future__ import annotations

from uuid import uuid4

import pytest

from lib.search.indexing.render_commit import prepare_render_commits
from lib.storage import StorageError
from tests.unit.search.indexing.test_render_verification import asset_and_data


def test_staged_exact_render_restores_cleanup_winner_and_replays_without_replacement(tmp_path):
    storage, stored, asset, data = asset_and_data(tmp_path)
    with prepare_render_commits((asset,), storage) as prepared:
        stored.path.unlink()
        prepared.commit_under_content_locks()
        assert prepared.committed[0].created
        assert stored.path.read_bytes() == data
    inode = stored.path.stat().st_ino
    with prepare_render_commits((asset,), storage) as replay:
        replay.commit_under_content_locks()
        assert not replay.committed[0].created
    assert stored.path.stat().st_ino == inode
    assert all(not staged.temp_path.exists() for _, staged, _ in prepared.staged + replay.staged)


def test_mid_batch_blob_failure_cleans_recreated_object_after_rollback(tmp_path, monkeypatch):
    storage, stored, asset, data = asset_and_data(tmp_path)
    second_store = storage.store_bytes(data, kind="derived", role="other")
    second = asset.model_copy(
        update={
            "id": uuid4(),
            "page_id": uuid4(),
            "page_number": 2,
            "uri": second_store.uri,
            "source": asset.source.model_copy(update={"page_number": 2}),
        }
    )
    cleaned = []

    def cleanup(value):
        cleaned.append(value)
        if value.created:
            value.path.unlink()

    monkeypatch.setattr(
        "lib.search.indexing.render_commit.cleanup_unreferenced_stored_object", cleanup
    )
    with pytest.raises(StorageError):
        with prepare_render_commits((asset, second), storage) as prepared:
            stored.path.unlink()
            second_store.path.write_bytes(b"Controlled existing-object corruption")
            prepared.commit_under_content_locks()
    assert len(cleaned) == 1 and cleaned[0].created and not stored.path.exists()
    assert second_store.path.exists()
    assert all(not staged.temp_path.exists() for _, staged, _ in prepared.staged)


def test_invalid_inventory_cannot_start_staging(tmp_path, monkeypatch):
    from lib.search.indexing.errors import IndexCandidateError

    storage, _, asset, _ = asset_and_data(tmp_path)
    monkeypatch.setattr(
        storage, "stage_stream", lambda *a, **k: pytest.fail("Invalid inventory staged bytes")
    )
    with pytest.raises(IndexCandidateError):
        with prepare_render_commits((asset, asset), storage):
            pytest.fail("Invalid inventory admitted")
