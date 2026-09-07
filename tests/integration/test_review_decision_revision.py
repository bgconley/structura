from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Event
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from lib.contracts import ReviewActionRequest
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.review import action_repository
from lib.review.correction_revision import CorrectionConflictError
from lib.review.service import ReviewService

from .test_completion_authorization import wait_until_blocked
from .test_human_confirmed_promotion import candidate, confirm, promote, snapshot
from .test_human_confirmed_promotion import promotion_document as promotion_document

MISSING = object()


def decide(document_id, access, item, action, revision=MISSING):
    payload = {
        "documentId": str(document_id),
        "actionType": action,
        "fieldPath": item["field_path"],
        "metadata": {
            "candidateId": str(item["id"]),
            "ordinal": item["ordinal"],
            "valueType": "string",
        },
        "newValue": "PO-NEW-HUMAN-VALUE" if action == "correct_field" else str(item["id"]),
        "evidenceContext": [{"pageNumber": 1, "sourceEngine": "human"}],
        "comment": "Explicit field decision",
    }
    if revision is not MISSING:
        payload["expectedUpdatedAt"] = revision
    return ReviewService().apply_review_action(
        ReviewActionRequest.model_validate(payload), access=access, actor_user_id=access.user_id
    )


def decision_snapshot(document_id):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT
              (SELECT count(*) FROM review_events WHERE document_id=%(id)s) AS events,
              (SELECT count(*) FROM pipeline_jobs WHERE document_id=%(id)s) AS jobs,
              (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM field_candidates c
                WHERE document_id=%(id)s) AS candidates""",
            {"id": document_id},
        )
        return snapshot(document_id), cur.fetchone()


@pytest.mark.parametrize("action", ["correct_field", "confirm_field", "reject_field"])
@pytest.mark.parametrize("marker", ["source_kind", "user_corrected", "deleted_actor"])
def test_legacy_and_deleted_actor_human_decisions_require_revision(
    promotion_document, action, marker
):
    document_id, access = promotion_document
    item = candidate(document_id, "PO-PRESERVED")
    if marker == "deleted_actor":
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email,display_name) VALUES (%s,'Former reviewer') RETURNING id",
                (f"former-reviewer-{uuid4()}@example.com",),
            )
            former = cur.fetchone()["id"]
            cur.execute(
                "INSERT INTO household_memberships (household_id,user_id,role) "
                "VALUES (%s,%s,'admin')",
                (access.household_id, former),
            )
        confirm(
            document_id,
            DocumentAccessContext(access.household_id, former, "admin"),
            item,
        )
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id=%s", (former,))
        assert snapshot(document_id)[0]["accepted_by_user_id"] is None
    else:
        assert promote(document_id, item) == 1
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE canonical_fields SET source_kind=%s,review_status=%s WHERE document_id=%s",
                (
                    "human" if marker == "source_kind" else "candidate",
                    "auto_accepted" if marker == "source_kind" else "user_corrected",
                    document_id,
                ),
            )
    before = decision_snapshot(document_id)
    with pytest.raises(CorrectionConflictError):
        decide(document_id, access, item, action)
    assert decision_snapshot(document_id) == before
    revision = before[0][0]["updated_at"].isoformat()
    assert decide(document_id, access, item, action, revision)["ok"]
    assert len(snapshot(document_id)[1]) == len(before[0][1]) + 1


@pytest.mark.parametrize("action", ["confirm_field", "reject_field"])
def test_first_decision_and_explicit_current_revision_remain_supported(promotion_document, action):
    document_id, access = promotion_document
    item = candidate(document_id, "PO-FIRST")
    assert promote(document_id, item) == 1
    assert decide(document_id, access, item, action)["ok"]
    # Confirmation establishes human authority; explicit current revision still
    # authorizes a subsequent human change rather than permanently freezing it.
    current = snapshot(document_id)[0]
    replacement = candidate(document_id, "PO-EXPLICIT-REPLACEMENT")
    assert decide(
        document_id, access, replacement, "confirm_field", current["updated_at"].isoformat()
    )["ok"]
    selected = snapshot(document_id)[0]
    assert selected["text_value"] == "PO-EXPLICIT-REPLACEMENT"
    assert selected["selected_candidate_id"] == replacement["id"]


@pytest.mark.parametrize("action", ["confirm_field", "reject_field"])
def test_waiting_decision_rechecks_revision_after_real_concurrent_correction(
    promotion_document, monkeypatch, action
):
    document_id, access = promotion_document
    item = candidate(document_id, "PO-OLD")
    confirm(document_id, access, item)
    before = decision_snapshot(document_id)
    old_revision = before[0][0]["updated_at"].isoformat()
    checking = Queue()
    written, release = Event(), Event()
    original_assert = action_repository.assert_writable
    original_upsert = action_repository._upsert_canonical_row

    def observe_lock(cur, *args):
        checking.put(cur.connection.info.backend_pid)
        return original_assert(cur, *args)

    def pause_human_write(cur, **kwargs):
        result = original_upsert(cur, **kwargs)
        if kwargs["source_kind"] == "human":
            written.set()
            if not release.wait(timeout=10):
                raise AssertionError("Test did not release the real correction transaction")
        return result

    monkeypatch.setattr(action_repository, "assert_writable", observe_lock)
    monkeypatch.setattr(action_repository, "_upsert_canonical_row", pause_human_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        correction = pool.submit(decide, document_id, access, item, "correct_field", old_revision)
        correction_pid = checking.get(timeout=5)
        assert written.wait(timeout=5)
        waiting = pool.submit(decide, document_id, access, item, action, old_revision)
        try:
            waiting_pid = checking.get(timeout=5)
            with db_connection() as conn, conn.cursor() as cur:
                wait_until_blocked(cur, correction_pid, waiting_pid)
        finally:
            release.set()
        assert correction.result(timeout=5)["ok"]
        with pytest.raises(CorrectionConflictError):
            waiting.result(timeout=5)
    current, counts = decision_snapshot(document_id)
    assert current[0]["text_value"] == "PO-NEW-HUMAN-VALUE"
    assert current[0]["source_kind"] == "human"
    assert current[0]["review_status"] == "user_corrected"
    assert current[0]["updated_at"] > before[0][0]["updated_at"]
    assert len(current[1]) == len(before[0][1]) + 1
    assert counts["events"] == before[1]["events"] + 1
    assert counts["jobs"] == before[1]["jobs"] + 1
    assert counts["candidates"] == before[1]["candidates"]


@pytest.mark.parametrize("action", ["correct_field", "confirm_field", "reject_field"])
def test_field_decision_preserves_other_ordinals_and_unrelated_candidate_tasks(
    promotion_document, action
):
    document_id, access = promotion_document
    first = candidate(document_id, "PO-FIRST-ORDINAL")
    second = candidate(document_id, "PO-SECOND-ORDINAL")
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE field_candidates SET ordinal=2 WHERE id=%s RETURNING *", (second["id"],)
        )
        second = cur.fetchone()
    confirm(document_id, access, first)
    confirm(document_id, access, second)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM canonical_fields WHERE document_id=%s ORDER BY ordinal", (document_id,)
        )
        previous = cur.fetchall()
        cur.execute(
            "INSERT INTO documents (ingestion_source,household_id,owner_user_id) "
            "VALUES ('web_upload',%s,%s) RETURNING id",
            (access.household_id, access.user_id),
        )
        other_document = cur.fetchone()["id"]
        invalid_refs = []
        for candidate_document, path in [
            (other_document, first["field_path"]),
            (document_id, "invoice.other_field"),
        ]:
            cur.execute(
                "INSERT INTO field_candidates "
                "(document_id,field_path,ordinal,source_engine,value_type,text_value) "
                "VALUES (%s,%s,2,'validator','string','Unrelated') RETURNING id",
                (candidate_document, path),
            )
            invalid_refs.append(str(cur.fetchone()["id"]))
        task_metadata = [
            {"candidateId": str(first["id"])},
            {"candidateId": str(second["id"])},
            {"ordinal": 2},
            {"candidateId": invalid_refs[0]},
            {"candidateId": invalid_refs[1]},
            {},  # Legacy task without identity refers to ordinal one only.
            {"candidateId": str(second["id"]), "ordinal": 1},
        ]
        tasks = []
        for metadata in task_metadata:
            cur.execute(
                "INSERT INTO review_tasks (document_id,task_type,status,metadata_json) "
                "VALUES (%s,'field_review','open',%s) RETURNING id",
                (document_id, Jsonb({"fieldPath": first["field_path"], **metadata})),
            )
            tasks.append(cur.fetchone()["id"])
    assert decide(document_id, access, second, action, previous[1]["updated_at"].isoformat())["ok"]
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM canonical_fields WHERE document_id=%s AND ordinal=1", (document_id,)
        )
        assert cur.fetchone() == previous[0]
        cur.execute("SELECT status FROM field_candidates WHERE id=%s", (first["id"],))
        assert cur.fetchone()["status"] == "promoted"
        cur.execute("SELECT id,status FROM review_tasks WHERE document_id=%s", (document_id,))
        statuses = {row["id"]: row["status"] for row in cur.fetchall()}
        assert [statuses[task] for task in tasks] == [
            "open",
            "resolved",
            "resolved",
            "open",
            "open",
            "open",
            "open",
        ]
