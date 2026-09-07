from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from queue import Queue
from threading import Event
from uuid import uuid4

import pytest

from lib.db.connection import db_connection
from lib.evidence import write_repository
from lib.evidence.blob_commit import prepare_render_commit
from lib.evidence.errors import EvidenceUnavailable
from lib.evidence.read_service import GenerationEvidenceReader
from lib.jobs import JobOwnershipLost
from lib.jobs.operator_repository import cancel_job
from lib.storage.reference_cleanup import _is_object_referenced, lock_content_hash
from tests.integration.evidence.conftest import populate
from tests.integration.search.indexing.test_authority_races import wait_for_lock


@pytest.mark.parametrize("revocation", ["cancel", "expire"])
def test_fresh_claim_fence_rolls_back_page_after_waiting_for_job_lock(evidence, revocation):
    processing, _, claimed, writer, binding, asset, _ = evidence
    pids = Queue()

    def publish():
        with prepare_render_commit(asset, writer.storage) as prepared:
            with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
                pids.put(conn.info.backend_pid)
                write_repository.register_asset(
                    cur, binding, asset, commit_source=prepared.commit_under_content_lock
                )
                conn.commit()

    with db_connection() as conn, conn.cursor() as cur:
        if revocation == "cancel":
            cancel_job(
                cur,
                job_id=claimed.state.job_id,
                household_id=processing.access.household_id,
                reason="safe",
                include_running=True,
                requested_by="test",
            )
        else:
            cur.execute(
                "SELECT id FROM pipeline_jobs WHERE id=%s FOR UPDATE", (claimed.state.job_id,)
            )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(publish)
            wait_for_lock(pids.get(timeout=5))
            if revocation == "expire":
                cur.execute(
                    "UPDATE pipeline_jobs SET "
                    "lease_expires_at=clock_timestamp()-interval '1 second' "
                    "WHERE id=%s",
                    (claimed.state.job_id,),
                )
            conn.commit()
            with pytest.raises(JobOwnershipLost):
                future.result(timeout=5)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_render_assets WHERE id=%s", (asset.id,)
        )
        assert cur.fetchone()["n"] == 0


def test_cleanup_reference_check_waits_for_page_publication_and_keeps_bytes(evidence):
    processing, _, claimed, writer, binding, asset, stored = evidence
    pids = Queue()

    def reference_check():
        with db_connection() as conn, conn.cursor() as cur:
            pids.put(conn.info.backend_pid)
            lock_content_hash(cur, stored.sha256)
            return _is_object_referenced(cur, stored)

    with (
        prepare_render_commit(asset, writer.storage) as prepared,
        processing.scope(claimed),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        write_repository.register_asset(
            cur, binding, asset, commit_source=prepared.commit_under_content_lock
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(reference_check)
            wait_for_lock(pids.get(timeout=5))
            conn.commit()
            assert future.result(timeout=5) is True
    assert stored.path.exists()


@pytest.mark.parametrize("revocation", ["scopes", "revoke", "expire", "membership"])
def test_live_read_authority_is_rechecked_after_media_io_on_separate_connection(
    evidence, monkeypatch, revocation
):
    processing, run, _, writer, _, _, _ = evidence
    populate(evidence)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO api_tokens (user_id,household_id,label,token_hash,scopes) "
            "VALUES (%s,%s,'Evidence test',%s,ARRAY['documents:read']) RETURNING id",
            (processing.access.user_id, processing.access.household_id, str(uuid4())),
        )
        token = cur.fetchone()["id"]
        conn.commit()
    access = replace(processing.access, api_token_id=token, scopes=("documents:read",))
    from lib.evidence import read_service

    original = read_service.snapshot_render
    entered, released = Event(), Event()
    snapshots = []

    def snapshot(*args):
        result = original(*args)
        snapshots.append(result)
        entered.set()
        assert released.wait(5)
        return result

    monkeypatch.setattr(read_service, "snapshot_render", snapshot)
    reader = GenerationEvidenceReader(writer.storage)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            reader.render, processing.document_id, run.binding.parse_generation_id, 1, access
        )
        assert entered.wait(5)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                if revocation == "membership":
                    cur.execute(
                        "DELETE FROM household_memberships WHERE household_id=%s AND user_id=%s",
                        (access.household_id, access.user_id),
                    )
                elif revocation == "scopes":
                    cur.execute(
                        "UPDATE api_tokens SET scopes=ARRAY['jobs:admin'] WHERE id=%s", (token,)
                    )
                elif revocation == "revoke":
                    cur.execute(
                        "UPDATE api_tokens SET revoked_at=clock_timestamp() WHERE id=%s", (token,)
                    )
                else:
                    cur.execute(
                        "UPDATE api_tokens SET expires_at=clock_timestamp()-interval '1 second' "
                        "WHERE id=%s",
                        (token,),
                    )
                conn.commit()
        finally:
            released.set()
        with pytest.raises(EvidenceUnavailable):
            future.result(timeout=5)
    assert snapshots[0].stream.closed


@pytest.mark.parametrize("cancel_after_blob_commit", [False, True])
def test_cleanup_wins_after_preverification_then_exact_blob_commit_restores_before_reference(
    evidence, monkeypatch, cancel_after_blob_commit
):
    from lib.jobs import JobService
    from lib.storage import cleanup_unreferenced_stored_object

    processing, _, claimed, writer, binding, asset, stored = evidence
    # The ingestion caller can have reused a file; the eventual publication copy
    # must still track that it recreated the destination after cleanup removed it.
    reused = writer.storage.store_bytes(
        stored.path.read_bytes(), kind="derived", role="source-page"
    )
    assert not reused.created and reused.uri == asset.uri
    prepared, cleaned, committed, release = Event(), Event(), Event(), Event()
    original = write_repository.register_asset

    def register(cur, bound, value, *, commit_source):
        prepared.set()
        assert cleaned.wait(5)
        assert not stored.path.exists()

        def commit_blob():
            commit_source()
            assert stored.path.exists()
            committed.set()
            assert release.wait(5)

        return original(cur, bound, value, commit_source=commit_blob)

    monkeypatch.setattr(write_repository, "register_asset", register)

    def publish():
        with processing.scope(claimed):
            return writer.checkpoint(binding, asset)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(publish)
        assert prepared.wait(5)
        cleanup_unreferenced_stored_object(
            stored
        )  # Separate committed SQL connection wins hash lock.
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
            assert future.result(timeout=5) == asset.fingerprint
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_render_assets WHERE id=%s", (asset.id,)
        )
        assert cur.fetchone()["n"] == (0 if cancel_after_blob_commit else 1)
    assert stored.path.exists() is not cancel_after_blob_commit
    if not cancel_after_blob_commit:
        with processing.scope(claimed):
            writer.seal(binding)
