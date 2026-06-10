from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from lib.contracts import ReviewActionRequest
from lib.documents.access_policy import DocumentAccessContext
from lib.review.service import ReviewService, ReviewServiceError

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
ACTOR_ID = UUID("22222222-2222-4222-8222-222222222222")
EVENT_ID = UUID("33333333-3333-4333-8333-333333333333")


def _action(action_type: str, metadata: dict[str, Any] | None) -> ReviewActionRequest:
    return ReviewActionRequest.model_validate(
        {
            "schemaName": "review_action",
            "schemaVersion": "v1",
            "documentId": DOCUMENT_ID,
            "actionType": action_type,
            "actorType": "human",
            "metadata": metadata,
            "comment": "Decision from review queue.",
            "createdAt": "2026-06-09T00:00:00Z",
        }
    )


def _access() -> DocumentAccessContext:
    return DocumentAccessContext(
        household_id=uuid4(),
        user_id=ACTOR_ID,
        household_role="admin",
    )


@pytest.mark.parametrize(
    ("action_type", "expected_decision"),
    [("accept_observation", "accept"), ("reject_observation", "reject")],
)
def test_observation_decisions_route_to_decision_repository(
    monkeypatch: pytest.MonkeyPatch,
    action_type: str,
    expected_decision: str,
) -> None:
    observation_id = uuid4()
    captured: dict[str, Any] = {}

    def fake_decide_observation(**kwargs: Any) -> UUID:
        captured.update(kwargs)
        return EVENT_ID

    monkeypatch.setattr(
        "lib.review.repository.decide_observation",
        fake_decide_observation,
    )

    result = ReviewService().apply_review_action(
        _action(action_type, {"observationId": str(observation_id)}),
        access=_access(),
        actor_user_id=ACTOR_ID,
    )

    assert result == {"ok": True, "reviewEventId": str(EVENT_ID)}
    assert captured["observation_id"] == observation_id
    assert captured["decision"] == expected_decision
    assert captured["document_id"] == DOCUMENT_ID


@pytest.mark.parametrize(
    ("action_type", "expected_decision"),
    [("accept_line_item", "accept"), ("reject_line_item", "reject")],
)
def test_line_item_decisions_route_to_decision_repository(
    monkeypatch: pytest.MonkeyPatch,
    action_type: str,
    expected_decision: str,
) -> None:
    candidate_id = uuid4()
    captured: dict[str, Any] = {}

    def fake_decide_line_item(**kwargs: Any) -> UUID:
        captured.update(kwargs)
        return EVENT_ID

    monkeypatch.setattr(
        "lib.review.repository.decide_line_item",
        fake_decide_line_item,
    )

    result = ReviewService().apply_review_action(
        _action(action_type, {"lineItemCandidateId": str(candidate_id)}),
        access=_access(),
        actor_user_id=ACTOR_ID,
    )

    assert result == {"ok": True, "reviewEventId": str(EVENT_ID)}
    assert captured["candidate_id"] == candidate_id
    assert captured["decision"] == expected_decision


def test_observation_decision_requires_observation_id() -> None:
    with pytest.raises(ReviewServiceError, match="observationId"):
        ReviewService().apply_review_action(
            _action("accept_observation", None),
            access=_access(),
            actor_user_id=ACTOR_ID,
        )


def test_line_item_decision_requires_candidate_id() -> None:
    with pytest.raises(ReviewServiceError, match="lineItemCandidateId"):
        ReviewService().apply_review_action(
            _action("reject_line_item", {}),
            access=_access(),
            actor_user_id=ACTOR_ID,
        )
