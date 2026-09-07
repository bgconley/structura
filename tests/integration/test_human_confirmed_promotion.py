from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from queue import Queue
from threading import Event
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.extraction.canonical_repository import promote_candidates
from lib.extraction.extraction_repository import _lock_document
from lib.extraction.models import ValidationReport
from lib.extraction.source_repository import load_extraction_source
from lib.review import action_repository


@pytest.fixture
def promotion_document(monkeypatch):
    url = os.environ.get("STRUCTURA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires an isolated migrated database.")
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    owner = AuthService().bootstrap_admin(
        email=f"human-confirmed-{uuid4()}@example.com",
        password="minimum8",
        household_name=f"Human confirmed {uuid4()}",
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO documents (title,ingestion_source,household_id,owner_user_id)
            VALUES ('Human decision','web_upload',%s,%s) RETURNING id""",
            (owner.household_id, owner.user_id),
        )
        document_id = cur.fetchone()["id"]
    yield document_id, DocumentAccessContext(owner.household_id, owner.user_id, "owner")
    get_settings.cache_clear()


def candidate(document_id, text):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE document_extractions SET is_current=false WHERE document_id=%s",
            (document_id,),
        )
        cur.execute(
            """INSERT INTO document_extractions
            (document_id,schema_name,schema_version,status,source_engine)
            VALUES (%s,'invoice','v1','completed','validator') RETURNING id""",
            (document_id,),
        )
        extraction_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO field_candidates
            (document_id,extraction_id,field_path,source_engine,value_type,text_value,
             evidence_json,validation_json)
            VALUES (%s,%s,'invoice.purchase_order','validator','string',%s,%s,%s) RETURNING *""",
            (document_id, extraction_id, text, Jsonb([{"pageNumber": 1}]), Jsonb({"valid": True})),
        )
        return cur.fetchone()


def confirm(document_id, access, item):
    return action_repository.confirm_candidate(
        document_id=document_id,
        access=access,
        actor_user_id=access.user_id,
        candidate_id=item["id"],
        reason="Confirmed from original evidence",
    )


def promote(document_id, item, pids=None):
    source = load_extraction_source(document_id)
    with db_connection() as conn, conn.cursor() as cur:
        if pids is not None:
            pids.put(conn.info.backend_pid)
        # Same document serialization used by _persist_extraction_rows before
        # candidate promotion and by every canonical review mutation.
        _lock_document(cur, document_id)
        count = promote_candidates(
            cur,
            source=source,
            extraction_id=item["extraction_id"],
            candidates=[item],
            validation=ValidationReport(needs_review=False, checks=[]),
            schema_name="invoice",
        )
        conn.commit()
        return count


def snapshot(document_id):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM canonical_fields WHERE document_id=%s", (document_id,))
        canonical = cur.fetchone()
        cur.execute(
            "SELECT * FROM canonical_fact_history WHERE document_id=%s ORDER BY created_at,id",
            (document_id,),
        )
        history = cur.fetchall()
        return canonical, history


def test_confirmed_candidate_survives_conflicting_automatic_rerun(promotion_document):
    document_id, access = promotion_document
    original = candidate(document_id, "PO-USER-CONFIRMED")
    confirm(document_id, access, original)
    before = snapshot(document_id)
    assert before[0]["source_kind"] == "candidate"
    assert before[0]["review_status"] == "user_confirmed"
    replacement = candidate(document_id, "PO-AUTOMATIC-RERUN")
    assert promote(document_id, replacement) == 0
    assert snapshot(document_id) == before
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM field_candidates WHERE id=%s", (replacement["id"],))
        assert cur.fetchone()["status"] == "proposed"


@pytest.mark.parametrize("source_kind", ["candidate", "validator", "system"])
def test_system_acceptance_without_human_decision_can_still_refresh(
    promotion_document, source_kind
):
    document_id, _ = promotion_document
    original = candidate(document_id, "PO-AUTO-OLD")
    assert promote(document_id, original) == 1
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE canonical_fields SET source_kind=%s WHERE document_id=%s",
            (source_kind, document_id),
        )
    replacement = candidate(document_id, "PO-AUTO-NEW")
    assert promote(document_id, replacement) == 1
    current, history = snapshot(document_id)
    assert current["text_value"] == "PO-AUTO-NEW" and current["accepted_by_user_id"] is None
    assert current["review_status"] == "auto_accepted" and len(history) == 2


def test_retained_accepting_actor_protects_legacy_status_representation(promotion_document):
    document_id, access = promotion_document
    original = candidate(document_id, "PO-HUMAN-ATTRIBUTED")
    assert promote(document_id, original) == 1
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE canonical_fields SET accepted_by_user_id=%s WHERE document_id=%s",
            (access.user_id, document_id),
        )
    before = snapshot(document_id)
    assert promote(document_id, candidate(document_id, "PO-LATER")) == 0
    assert snapshot(document_id) == before


def test_waiting_automatic_rerun_observes_committed_human_confirmation(
    promotion_document, monkeypatch
):
    document_id, access = promotion_document
    original = candidate(document_id, "PO-CONFIRMED-DURING-RERUN")
    replacement = candidate(document_id, "PO-LATE-AUTOMATIC")
    confirming = Queue()
    publishing = Queue()
    release = Event()

    class PausedReviewCommit:
        def __init__(self, conn):
            self.conn = conn

        def cursor(self):
            return self.conn.cursor()

        def commit(self):
            confirming.put(self.conn.info.backend_pid)
            if not release.wait(timeout=10):
                raise AssertionError("Test did not release the review transaction")
            self.conn.commit()

    @contextmanager
    def paused_review_connection():
        with db_connection() as conn:
            yield PausedReviewCommit(conn)

    monkeypatch.setattr(action_repository, "db_connection", paused_review_connection)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reviewed = pool.submit(confirm, document_id, access, original)
        review_pid = confirming.get(timeout=5)
        rerun = pool.submit(promote, document_id, replacement, publishing)
        try:
            rerun_pid = publishing.get(timeout=5)
            deadline = time.monotonic() + 5
            with db_connection() as conn, conn.cursor() as cur:
                while time.monotonic() < deadline:
                    cur.execute("SELECT pg_blocking_pids(%s) AS blockers", (rerun_pid,))
                    if review_pid in cur.fetchone()["blockers"]:
                        break
                    time.sleep(0.01)
                else:
                    raise AssertionError("Automatic rerun did not wait for the real review lock")
        finally:
            release.set()
        assert reviewed.result(timeout=5) is not None
        assert rerun.result(timeout=5) == 0
    current, history = snapshot(document_id)
    assert current["selected_candidate_id"] == original["id"]
    assert current["review_status"] == "user_confirmed"
    assert current["text_value"] == "PO-CONFIRMED-DURING-RERUN"
    assert current["accepted_by_user_id"] == access.user_id
    assert len(history) == 1 and history[0]["action"] == "human_confirmed"
