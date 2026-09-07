import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event

import pytest

from lib.contracts import FolderWrite, TagWrite
from lib.db.connection import db_connection
from lib.organization import authority_repository, manual_filing
from lib.organization.policy import OrganizationError

from ..legacy_uploads.support import revoke
from ..line_items.support import token_document
from ..test_completion_authorization import observe_lock_backend
from ..test_completion_session_security import wait_for_blocked
from .support import established_facts, file_document, impact


@pytest.mark.parametrize("change", ["session_row", "token_scope", "role"])
def test_filing_rechecks_original_credential_after_a_real_authority_lock_wait(
    organization_document, monkeypatch, change
):
    doc = organization_document
    if change == "token_scope":
        doc, _ = token_document(doc, ["documents:read", "documents:write"])
    before = impact(doc)
    backends = observe_lock_backend(monkeypatch, authority_repository, "lock_request_authority")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            revoke(cur, doc, change)
            pending = pool.submit(file_document, doc, title="Denied filing")
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            with pytest.raises(OrganizationError) as failure:
                pending.result(timeout=5)
    assert failure.value.status_code == 403 and failure.value.detail == "Permission denied"
    assert impact(doc) == before


@pytest.mark.parametrize("kind", ["folder", "tag"])
def test_catalog_create_cannot_publish_after_waiting_for_session_revocation(
    organization_document, monkeypatch, kind
):
    doc = organization_document
    backends = observe_lock_backend(monkeypatch, authority_repository, "lock_request_authority")
    create, body = (
        (manual_filing.create_folder, FolderWrite(folderKind="manual", name="Denied folder"))
        if kind == "folder"
        else (manual_filing.create_tag, TagWrite(name="Denied tag"))
    )
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            revoke(cur, doc, "session_row")
            pending = pool.submit(create, body, doc.principal)
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            with pytest.raises(OrganizationError) as failure:
                pending.result(timeout=5)
    assert failure.value.status_code == 403
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT (SELECT count(*) FROM folders WHERE household_id=%s) AS folders,"
            "(SELECT count(*) FROM tags WHERE household_id=%s) AS tags",
            (doc.credential.household_id, doc.credential.household_id),
        )
        assert cur.fetchone() == {"folders": 0, "tags": 0}


def test_expiry_after_actual_filing_projection_and_enqueue_rolls_everything_back(
    organization_document, monkeypatch
):
    doc = organization_document
    established_facts(doc)
    before = impact(doc)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE sessions SET expires_at=clock_timestamp()+interval '3 seconds' "
            "WHERE id=%s RETURNING expires_at",
            (doc.credential.session_id,),
        )
        deadline = cur.fetchone()["expires_at"]
    staged, release = Queue(), Event()
    original = manual_filing.refresh_metadata_and_enqueue

    def pause_after_real_writes(cur, **kwargs):
        original(cur, **kwargs)
        cur.execute("SELECT title FROM documents WHERE id=%s", (doc.document_id,))
        assert cur.fetchone()["title"] == "Uncommitted filing"
        cur.execute(
            "SELECT count(*) AS n FROM pipeline_jobs WHERE document_id=%s", (doc.document_id,)
        )
        assert cur.fetchone()["n"] == len(before["fields"]["jobs"]) + 1
        staged.put(True)
        if not release.wait(10):
            raise AssertionError("Final credential fence was not released")

    monkeypatch.setattr(manual_filing, "refresh_metadata_and_enqueue", pause_after_real_writes)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(file_document, doc, title="Uncommitted filing")
        try:
            staged.get(timeout=5)
            with db_connection() as conn, conn.cursor() as cur:
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    cur.execute("SELECT clock_timestamp()>=%s AS expired", (deadline,))
                    if cur.fetchone()["expired"]:
                        break
                    time.sleep(0.01)
                else:
                    raise AssertionError("DB clock did not reach credential expiry")
        finally:
            release.set()
        with pytest.raises(OrganizationError) as failure:
            pending.result(timeout=5)
    assert failure.value.status_code == 403
    assert impact(doc) == before
