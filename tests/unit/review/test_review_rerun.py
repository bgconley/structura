from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import lib.review.service as review_service_module
from lib.contracts import ReviewActionRequest
from lib.documents.access_policy import DocumentAccessContext
from lib.review.service import ReviewService, _target_schema_from_action

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
ACTOR_ID = UUID("22222222-2222-4222-8222-222222222222")


def _action(metadata: dict[str, Any] | None = None) -> ReviewActionRequest:
    return ReviewActionRequest.model_validate(
        {
            "schemaName": "review_action",
            "schemaVersion": "v1",
            "documentId": DOCUMENT_ID,
            "actionType": "rerun_extraction",
            "actorType": "human",
            "metadata": metadata,
            "comment": "Re-run requested from review queue.",
            "createdAt": "2026-06-09T00:00:00Z",
        }
    )


def _access() -> DocumentAccessContext:
    return DocumentAccessContext(
        household_id=uuid4(),
        user_id=ACTOR_ID,
        household_role="admin",
    )


class _FakeConnection:
    def __init__(self) -> None:
        self.committed = False

    @contextmanager
    def cursor(self):  # type: ignore[no-untyped-def]
        yield object()

    def commit(self) -> None:
        self.committed = True


def test_rerun_extraction_enqueues_smart_parse_semantic_annotation(monkeypatch) -> None:
    enqueued: dict[str, Any] = {}
    recorded: dict[str, Any] = {}
    connection = _FakeConnection()
    expected_job_id = uuid4()

    @contextmanager
    def fake_db_connection():  # type: ignore[no-untyped-def]
        yield connection

    def fake_enqueue(cur: Any, **kwargs: Any) -> UUID:
        enqueued.update(kwargs)
        return expected_job_id

    def fake_record_rerun_request(**kwargs: Any) -> UUID:
        recorded.update(kwargs)
        return UUID("33333333-3333-4333-8333-333333333333")

    monkeypatch.setattr(review_service_module, "db_connection", fake_db_connection)
    monkeypatch.setattr(review_service_module, "enqueue_semantic_annotation_job", fake_enqueue)
    monkeypatch.setattr(
        review_service_module.repository,
        "record_rerun_request",
        fake_record_rerun_request,
    )

    access = _access()
    result = ReviewService().apply_review_action(
        _action({"targetSchemaName": "invoice"}),
        access=access,
        actor_user_id=ACTOR_ID,
    )

    assert result["ok"] is True
    assert result["jobId"] == str(expected_job_id)
    assert result["reviewEventId"] == "33333333-3333-4333-8333-333333333333"
    # Rerun must flow through Smart Parse planning, never a broad
    # document-level Granite extract job that live routing rejects.
    assert enqueued["document_id"] == DOCUMENT_ID
    assert enqueued["household_id"] == access.household_id
    assert enqueued["quality_mode"] == "smart"
    assert enqueued["requested_by"] == "reviewer"
    assert enqueued["requested_by_user_id"] == ACTOR_ID
    assert enqueued["user_intent_reason"] == "Re-run requested from review queue."
    assert enqueued["reason"] == "review.rerun_extraction"
    assert enqueued["dedupe_existing"] is True
    assert connection.committed is True
    # The user-requested schema is recorded as audit lineage only.
    assert recorded["target_schema_name"] == "invoice"
    assert recorded["document_id"] == DOCUMENT_ID


def test_target_schema_from_action_no_longer_defaults_to_receipt() -> None:
    assert _target_schema_from_action(_action()) is None
    assert _target_schema_from_action(_action({"targetSchemaName": "invoice"})) == "invoice"
