import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event

import pytest

from lib.auth import session_repository
from lib.auth.authorization_policy import AuthorizationError
from lib.db.connection import db_connection
from lib.fact_authority import projection_repository
from lib.review.line_items import service
from lib.review.line_items.errors import LineDecisionConflict

from ..test_completion_authorization import observe_lock_backend
from ..test_completion_session_security import wait_for_blocked as wait_until_blocked
from .support import (
    candidate,
    create_request,
    decide,
    expected_source,
    snapshot,
    source,
    target,
    token_document,
)


@pytest.mark.parametrize("revoke", ["logout", "replacement", "disabled", "membership", "token"])
def test_original_request_authority_is_rechecked_after_real_lock_wait(
    line_document, monkeypatch, revoke
):
    doc = line_document
    if revoke == "token":
        doc, _ = token_document(doc, ["documents:review"])
    item = candidate(doc)
    request = create_request(doc, item)
    before = snapshot(doc)
    backends = observe_lock_backend(monkeypatch, service, "lock_line_review")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            if revoke == "logout":
                assert session_repository.revoke_authenticated_session(
                    cur, doc.credential.session_id, doc.credential.user_id
                )
            elif revoke == "replacement":
                assert session_repository.consume_session_replacement(
                    cur, doc.credential.session_id, doc.credential.user_id
                )
            elif revoke == "disabled":
                cur.execute(
                    "UPDATE users SET is_disabled=true WHERE id=%s", (doc.credential.user_id,)
                )
            elif revoke == "membership":
                cur.execute(
                    "DELETE FROM household_memberships WHERE user_id=%s AND household_id=%s",
                    (doc.credential.user_id, doc.credential.household_id),
                )
            else:
                cur.execute(
                    "UPDATE api_tokens SET revoked_at=clock_timestamp() WHERE id=%s",
                    (doc.credential.api_token_id,),
                )
            waiting = pool.submit(decide, doc, request)
            try:
                wait_until_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            with pytest.raises(AuthorizationError):
                waiting.result(timeout=5)
    assert snapshot(doc) == before


@pytest.mark.parametrize("stale_operation", ["replace", "reject_selected"])
def test_stale_line_decision_waits_then_cannot_overwrite_new_human_replacement(
    line_document, monkeypatch, stale_operation
):
    doc = line_document
    created = decide(doc, create_request(doc, candidate(doc)))
    canonical_id = created.canonical_item.id
    original_target = target(doc, canonical_id)
    newer_source = candidate(doc, "Newer human selection")
    stale = {"operation": stale_operation, "target": original_target}
    if stale_operation == "replace":
        stale["source"] = expected_source(source(doc, candidate(doc, "Older loaded proposal")))
    newer = {
        "operation": "replace",
        "source": expected_source(source(doc, newer_source)),
        "target": original_target,
    }
    published, release = Queue(), Event()
    original = service.refresh_projection_and_enqueue
    backends = observe_lock_backend(monkeypatch, service, "lock_line_review")

    def pause_after_projection(cur, **kwargs):
        result = original(cur, **kwargs)
        published.put(cur.connection.info.backend_pid)
        if not release.wait(10):
            raise AssertionError("Test did not release replacement")
        return result

    monkeypatch.setattr(service, "refresh_projection_and_enqueue", pause_after_projection)
    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(decide, doc, newer)
        winner_pid = published.get(timeout=5)
        assert backends.get(timeout=5) == winner_pid
        loser = pool.submit(decide, doc, stale)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                wait_until_blocked(cur, winner_pid, backends.get(timeout=5))
        finally:
            release.set()
        accepted = winner.result(timeout=5)
        with pytest.raises(LineDecisionConflict):
            loser.result(timeout=5)
    after = snapshot(doc)
    assert after["canonical"][0]["selected_candidate_id"] == str(newer_source)
    assert accepted.canonical_item.description == "Newer human selection"
    assert len(after["history"]) == len(after["jobs"]) == 2


def test_expiry_after_projection_and_enqueue_rolls_back_every_staged_effect(
    line_document, monkeypatch
):
    doc = line_document
    request = create_request(doc, candidate(doc))
    before = snapshot(doc)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE sessions SET expires_at=clock_timestamp()+interval '2 seconds' "
            "WHERE id=%s RETURNING expires_at",
            (doc.credential.session_id,),
        )
        deadline = cur.fetchone()["expires_at"]
    reached, release = Queue(), Event()
    original = service.refresh_projection_and_enqueue

    def pause_after_enqueue(cur, **kwargs):
        result = original(cur, **kwargs)
        reached.put(True)
        if not release.wait(7):
            raise AssertionError("Test did not release expiry boundary")
        return result

    monkeypatch.setattr(service, "refresh_projection_and_enqueue", pause_after_enqueue)
    with ThreadPoolExecutor(max_workers=1) as pool:
        deciding = pool.submit(decide, doc, request)
        reached.get(timeout=5)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    cur.execute("SELECT clock_timestamp()>=%s AS expired", (deadline,))
                    if cur.fetchone()["expired"]:
                        break
                    time.sleep(0.01)
                else:
                    raise AssertionError("Database clock did not reach credential expiry")
        finally:
            release.set()
        with pytest.raises(AuthorizationError):
            deciding.result(timeout=5)
    assert snapshot(doc) == before


@pytest.mark.parametrize("failure", ["refresh_accepted_projection", "enqueue_embed_document_job"])
def test_projection_and_enqueue_are_in_the_same_atomic_decision(
    line_document, monkeypatch, failure
):
    doc = line_document
    request = create_request(doc, candidate(doc))
    before = snapshot(doc)
    original = getattr(projection_repository, failure)

    def then_fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected after persistence")

    monkeypatch.setattr(projection_repository, failure, then_fail)
    with pytest.raises(RuntimeError, match="Injected after persistence"):
        decide(doc, request)
    assert snapshot(doc) == before


@pytest.mark.parametrize("same_source", [True, False])
def test_racing_source_assignment_and_vacant_target_have_one_winner(
    line_document, monkeypatch, same_source
):
    doc = line_document
    first = candidate(doc, "Concurrent first")
    second = first if same_source else candidate(doc, "Concurrent second")
    requests = [
        create_request(doc, first),
        create_request(doc, second, ordinal=2 if same_source else 1),
    ]
    backends = observe_lock_backend(monkeypatch, service, "lock_line_review")
    with ThreadPoolExecutor(max_workers=2) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            cur.execute("SELECT id FROM documents WHERE id=%s FOR UPDATE", (doc.document_id,))
            pending = [pool.submit(decide, doc, request) for request in requests]
            try:
                for _ in pending:
                    wait_until_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            results = []
            for future in pending:
                try:
                    results.append(future.result(timeout=5))
                except LineDecisionConflict:
                    results.append(None)
    assert sum(result is not None for result in results) == 1
    after = snapshot(doc)
    assert (
        len(after["canonical"])
        == len(after["bindings"])
        == len(after["history"])
        == len(after["jobs"])
        == 1
    )


def test_committed_extraction_supersession_denies_blocked_publication(line_document, monkeypatch):
    doc = line_document
    request = create_request(doc, candidate(doc))
    backends = observe_lock_backend(monkeypatch, service, "lock_line_review")
    with ThreadPoolExecutor(max_workers=1) as pool, db_connection() as blocker:
        with blocker.cursor() as cur:
            cur.execute("SELECT id FROM documents WHERE id=%s FOR UPDATE", (doc.document_id,))
            cur.execute(
                "UPDATE document_extractions SET is_current=false WHERE document_id=%s",
                (doc.document_id,),
            )
            deciding = pool.submit(decide, doc, request)
            try:
                wait_until_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            with pytest.raises(LineDecisionConflict):
                deciding.result(timeout=5)
    assert snapshot(doc)["canonical"] is None


def test_review_can_enqueue_while_supersession_waits_for_document(line_document, monkeypatch):
    doc = line_document
    request = create_request(doc, candidate(doc))
    ready, waiter, release = Queue(), Queue(), Event()
    original = service.refresh_projection_and_enqueue

    def pause_before_enqueue(cur, **kwargs):
        ready.put(cur.connection.info.backend_pid)
        if not release.wait(10):
            raise AssertionError("Test did not release publication")
        return original(cur, **kwargs)

    def supersede():
        with db_connection() as conn, conn.cursor() as cur:
            waiter.put(conn.info.backend_pid)
            cur.execute("SELECT id FROM documents WHERE id=%s FOR UPDATE", (doc.document_id,))
            cur.execute(
                "UPDATE document_extractions SET is_current=false WHERE document_id=%s",
                (doc.document_id,),
            )

    monkeypatch.setattr(service, "refresh_projection_and_enqueue", pause_before_enqueue)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deciding = pool.submit(decide, doc, request)
        pid = ready.get(timeout=5)
        superseding = pool.submit(supersede)
        try:
            with db_connection() as conn, conn.cursor() as cur:
                wait_until_blocked(cur, pid, waiter.get(timeout=5))
        finally:
            release.set()
        assert deciding.result(timeout=5).canonical_item.selected
        superseding.result(timeout=5)
    after = snapshot(doc)
    assert after["canonical"][0]["review_status"] == "user_confirmed"
    assert len(after["jobs"]) == 1
