from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from queue import Queue
from threading import Event

import pytest

from lib.db.connection import db_connection
from lib.review.line_items import service
from lib.review.line_items.errors import LineDecisionConflict
from lib.semantic_annotations.models import DocumentSemanticManifest, PageSemanticAnnotation
from lib.semantic_annotations.repository import (
    persist_semantic_manifest,
    persist_semantic_manifest_with_cursor,
)

from ..test_completion_authorization import observe_lock_backend
from ..test_completion_session_security import wait_for_blocked
from .support import candidate, create_request, decide, source


def aggregate_source(doc):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM document_pages WHERE document_id=%s AND page_number=1",
            (doc.document_id,),
        )
        page_id = cur.fetchone()["id"]
    manifest = DocumentSemanticManifest(
        document_id=doc.document_id,
        household_id=doc.credential.household_id,
        quality_mode="smart",
        profile_name="line-103-fixture",
        source_engine="validator",
        model_name="deterministic-test-fixture",
        model_version="v1",
        prompt_version="line-lock-test",
        pages=[PageSemanticAnnotation(page_id=page_id, page_number=1, page_role="body")],
        regions=[],
        confidence={},
        manifest={},
    )
    annotation = persist_semantic_manifest(manifest)
    item = candidate(doc, "Aggregate reviewed source")
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE document_extractions SET "
            "extraction_scope='aggregate',semantic_annotation_id=%s"
            "WHERE id=(SELECT extraction_id FROM line_item_candidates WHERE id=%s)",
            (annotation, item),
        )
    return item, replace(manifest, model_version="v2")


def test_semantic_supersession_commits_before_waiting_review_denies_old_aggregate(
    line_document, monkeypatch
):
    doc = line_document
    item, newer = aggregate_source(doc)
    request = create_request(doc, item)
    backends = observe_lock_backend(monkeypatch, service, "lock_line_review")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            persist_semantic_manifest_with_cursor(cur, newer)
            deciding = pool.submit(decide, doc, request)
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            with pytest.raises(LineDecisionConflict):
                deciding.result(timeout=5)
    assert source(doc, item)["publicationEligibility"]["reason"] == "source_superseded"


def test_shared_semantic_writer_takes_document_before_annotation_and_does_not_deadlock_review(
    line_document, monkeypatch
):
    doc = line_document
    item, newer = aggregate_source(doc)
    request = create_request(doc, item)
    ready, writer, release = Queue(), Queue(), Event()
    original = service.refresh_projection_and_enqueue

    def paused(cur, **kwargs):
        ready.put(cur.connection.info.backend_pid)
        if not release.wait(10):
            raise AssertionError("Test did not release line review")
        return original(cur, **kwargs)

    def supersede():
        with db_connection() as conn, conn.cursor() as cur:
            writer.put(conn.info.backend_pid)
            persist_semantic_manifest_with_cursor(cur, newer)

    monkeypatch.setattr(service, "refresh_projection_and_enqueue", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reviewing = pool.submit(decide, doc, request)
        pid = ready.get(timeout=5)
        superseding = pool.submit(supersede)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                wait_for_blocked(cur, pid, writer.get(timeout=5))
        finally:
            release.set()
        result = reviewing.result(timeout=5)
        superseding.result(timeout=5)
    assert result.canonical_item.selected
    assert source(doc, item)["publicationEligibility"]["reason"] == "source_superseded"
