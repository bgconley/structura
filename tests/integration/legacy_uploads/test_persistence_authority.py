import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from queue import Queue
from threading import Event

import pytest

from lib.auth.authorization_policy import AuthorizationError
from lib.db.connection import db_connection
from lib.documents import ingestion
from lib.documents.ingestion_admission import lock_original_admission
from lib.documents.ingestion_models import DocumentIngestionRequest

from ..test_completion_authorization import observe_lock_backend
from ..test_completion_session_security import wait_for_blocked
from .support import revoke


@pytest.mark.parametrize("credential_kind", ["session", "token"])
def test_admission_wait_precedes_fresh_credential_check_and_all_document_writes(
    legacy_upload, monkeypatch, credential_kind
):
    upload = legacy_upload.with_token() if credential_kind == "token" else legacy_upload
    before, files = upload.snapshot(), upload.files()
    backends = observe_lock_backend(monkeypatch, ingestion, "lock_original_admission")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            lock_original_admission(cur, upload.credential.household_id, upload.sha256)
            pending = pool.submit(upload.post)
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
                with db_connection() as revoked, revoked.cursor() as other:
                    revoke(other, upload, "token" if credential_kind == "token" else "logout")
            finally:
                blocker.commit()
            result = pending.result(timeout=5)
    assert result.status_code == 403 and result.json()["detail"] == "Permission denied"
    assert upload.snapshot() == before and upload.files() == files
    assert all(spool.closed for spool in upload.spools)


@pytest.mark.parametrize("credential_kind", ["session", "token"])
def test_original_credential_row_is_rechecked_after_the_real_revocation_wait(
    legacy_upload, monkeypatch, credential_kind
):
    upload = legacy_upload.with_token() if credential_kind == "token" else legacy_upload
    before = upload.snapshot()
    captured = upload.credential
    request = DocumentIngestionRequest(
        captured.household_id, captured.user_id, "web_upload", upload.filename
    )
    backends = observe_lock_backend(monkeypatch, ingestion, "lock_request_authority")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            revoke(cur, upload, "token_row" if credential_kind == "token" else "session_row")
            pending = pool.submit(
                ingestion.ingest_authenticated_document_stream,
                BytesIO(upload.content),
                request=request,
                credential=captured,
            )
            try:
                wait_for_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            with pytest.raises(AuthorizationError):
                pending.result(timeout=5)
    assert upload.snapshot() == before and upload.files() == {}


@pytest.mark.parametrize("credential_kind", ["session", "token"])
@pytest.mark.parametrize("shared_content", [False, True])
def test_absolute_expiry_after_real_publication_and_jobs_rolls_back_without_deleting_shared_content(
    legacy_upload, monkeypatch, credential_kind, shared_content
):
    upload = legacy_upload.with_token() if credential_kind == "token" else legacy_upload
    if shared_content:
        assert upload.post().status_code == 202
    before, files = upload.snapshot(), upload.files()
    with db_connection() as conn, conn.cursor() as cur:
        if credential_kind == "token":
            cur.execute(
                "UPDATE api_tokens SET expires_at=clock_timestamp()+interval '3 seconds' "
                "WHERE id=%s RETURNING expires_at",
                (upload.credential.api_token_id,),
            )
        else:
            cur.execute(
                "UPDATE sessions SET expires_at=clock_timestamp()+interval '3 seconds' "
                "WHERE id=%s RETURNING expires_at",
                (upload.credential.session_id,),
            )
        deadline = cur.fetchone()["expires_at"]
    staged, release = Queue(), Event()
    original = ingestion.create_ingestion_jobs

    def pause_after_real_jobs(cur, **kwargs):
        result = original(cur, **kwargs)
        # This proves actual object publication + SQL/job side effects happened,
        # rather than testing only an early permission check.
        assert kwargs["stored"].path.read_bytes() == upload.content
        cur.execute(
            "SELECT count(*) AS n FROM pipeline_jobs WHERE document_id=%s", (kwargs["document_id"],)
        )
        assert cur.fetchone()["n"] == 4
        staged.put(True)
        if not release.wait(10):
            raise AssertionError("Test did not release final expiry fence")
        return result

    monkeypatch.setattr(ingestion, "create_ingestion_jobs", pause_after_real_jobs)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(upload.post)
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
        result = pending.result(timeout=5)
    assert result.status_code == 403 and result.json()["detail"] == "Permission denied"
    assert upload.snapshot() == before and upload.files() == files
    assert all(spool.closed for spool in upload.spools)
