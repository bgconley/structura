from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from lib.db.connection import db_connection
from lib.jobs import JobOwnershipLost, JobService
from lib.search.indexing import input_repository
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.execution_inputs import prepare_index_candidate
from lib.storage import cleanup_unreferenced_stored_object
from tests.integration.search.indexing.conftest import asset_for, observation


@pytest.mark.parametrize("cancel_after_blob_commit", [False, True])
def test_cleanup_wins_before_registration_without_stranding_prepared_candidate(
    candidate_source, monkeypatch, cancel_after_blob_commit
):
    processing, run, claimed, service, checkpoint, stored = candidate_source
    config = index_configuration(model_mode="fixture")
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
    asset = asset_for(binding, checkpoint, stored)
    reused = service.storage.store_bytes(
        stored.path.read_bytes(), kind="derived", role="source-page"
    )
    assert not reused.created and reused.uri == asset.uri
    staged, cleaned, committed, release = Event(), Event(), Event(), Event()
    original = input_repository.prepare_inputs

    def prepare(cur, bound, assets, *, commit_sources):
        staged.set()
        assert cleaned.wait(5)
        assert not stored.path.exists()

        def commit():
            commit_sources()
            assert stored.path.exists()
            committed.set()
            assert release.wait(5)

        return original(cur, bound, assets, commit_sources=commit)

    monkeypatch.setattr(input_repository, "prepare_inputs", prepare)

    def publish():
        with processing.scope(claimed):
            return service.prepare(binding, (asset,))

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(publish)
        assert staged.wait(5)
        cleanup_unreferenced_stored_object(stored)  # Independent SQL transaction wins hash lock.
        assert not stored.path.exists()
        cleaned.set()
        assert committed.wait(5)
        try:
            if cancel_after_blob_commit:
                JobService().cancel_job(
                    job_id=claimed.state.job_id,
                    reason="Controlled cancellation",
                    include_running=True,
                )
        finally:
            release.set()
        if cancel_after_blob_commit:
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
        else:
            manifest = future.result(timeout=5)
    monkeypatch.setattr(input_repository, "prepare_inputs", original)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state,manifest_json FROM document_index_generations WHERE id=%s",
            (binding.index_generation_id,),
        )
        header = cur.fetchone()
        cur.execute(
            "SELECT count(*) AS n FROM document_generation_render_assets "
            "WHERE index_generation_id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone()["n"] == (0 if cancel_after_blob_commit else 1)
    if cancel_after_blob_commit:
        assert header == {"state": "preparing", "manifest_json": None}
        assert not stored.path.exists()
        return
    assert header["state"] == "embedding" and stored.path.exists()
    # Prepared replay consumes retained bytes; it does not rerender/model-call.
    monkeypatch.setattr(
        "lib.search.indexing.execution_inputs.DocumentSource",
        lambda *a, **k: pytest.fail("Prepared replay rerendered"),
    )
    with processing.scope(claimed):
        replay = prepare_index_candidate(binding, storage=service.storage, service=service)
        assert replay == manifest
        for item in manifest.inputs:
            service.checkpoint(binding, observation(item, config))
        completion = service.seal(binding)
        assert service.seal(binding) == completion
        assert service.missing_inputs(binding) == ()
