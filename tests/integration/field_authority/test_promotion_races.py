from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event

from lib.db.connection import db_connection
from lib.extraction.canonical_repository import promote_candidates
from lib.extraction.extraction_repository import _lock_document
from lib.extraction.models import ValidationReport
from lib.extraction.source_repository import load_extraction_source
from lib.review import canonical_field_repository as fields

from ..test_completion_authorization import observe_lock_backend, wait_until_blocked
from .support import candidate, envelope, promote, reject, snapshot
from .test_transactions import pause_after_projection


def test_waiting_promotion_observes_committed_rejection_without_canonical_row(
    promotion_document, monkeypatch
):
    document_id, access = promotion_document
    item = candidate(document_id, "Never restore this rejected candidate")
    completed, release = pause_after_projection(monkeypatch)
    pids = Queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        rejecting = pool.submit(reject, document_id, access, item["field_path"])
        rejection_pid = completed.get(timeout=5)
        promoting = pool.submit(promote, document_id, item, pids)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                wait_until_blocked(cur, rejection_pid, pids.get(timeout=5))
        finally:
            release.set()
        assert rejecting.result(timeout=5).canonical is None
        assert promoting.result(timeout=5) == 0
    current = envelope(document_id, access)
    assert current.items == [] and current.decisions[0].disposition == "rejected"


def test_waiting_first_rejection_removes_newly_committed_automatic_fact(
    promotion_document, monkeypatch
):
    document_id, access = promotion_document
    item = candidate(document_id, "Auto value that a human rejects")
    source = load_extraction_source(document_id)
    published, release = Queue(), Event()
    waiting = observe_lock_backend(monkeypatch, fields, "assert_writable")

    def publish_and_pause():
        with db_connection() as conn, conn.cursor() as cur:
            _lock_document(cur, document_id)
            count = promote_candidates(
                cur,
                source=source,
                extraction_id=item["extraction_id"],
                candidates=[item],
                validation=ValidationReport(needs_review=False, checks=[]),
                schema_name="invoice",
            )
            published.put(conn.info.backend_pid)
            if not release.wait(timeout=10):
                raise AssertionError("Test did not release automatic promotion")
            return count

    with ThreadPoolExecutor(max_workers=2) as pool:
        promoting = pool.submit(publish_and_pause)
        promotion_pid = published.get(timeout=5)
        rejecting = pool.submit(reject, document_id, access, item["field_path"])
        try:
            with db_connection() as conn, conn.cursor() as cur:
                wait_until_blocked(cur, promotion_pid, waiting.get(timeout=5))
        finally:
            release.set()
        assert promoting.result(timeout=5) == 1
        result = rejecting.result(timeout=5)
        assert result.canonical.review_status == "rejected"
    current = snapshot(document_id)
    assert [
        row["action"] for row in sorted(current["history"], key=lambda row: row["created_at"])
    ] == ["auto_promoted", "human_rejected"]
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS count FROM selected_canonical_fields WHERE document_id=%s",
            (document_id,),
        )
        assert cur.fetchone()["count"] == 0
