from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from lib.contracts import RelationshipWrite, SearchRequest
from lib.relationships.deadline_status import deadline_status
from lib.search.query import parse_search_request
from lib.search.saved_query import parse_saved_query


def test_phase7_search_request_parses_relationship_and_deadline_filters() -> None:
    request = SearchRequest.model_validate(
        {
            "query": "warranty paperwork",
            "relationshipTypes": ["warranty_for", "warranty_for"],
            "relationshipStatuses": ["confirmed"],
            "hasRelationships": True,
            "deadlineTypes": ["warranty_expiration"],
            "deadlineStatuses": ["open"],
            "hasOpenDeadlines": True,
        }
    )

    parsed = parse_search_request(request)

    assert parsed.filters.relationship_types == ("warranty_for",)
    assert parsed.filters.relationship_statuses == ("confirmed",)
    assert parsed.filters.has_relationships is True
    assert parsed.filters.deadline_types == ("warranty_expiration",)
    assert parsed.filters.deadline_statuses == ("open",)
    assert parsed.filters.has_open_deadlines is True
    assert parsed.filters.applied_count >= 6


def test_phase7_saved_query_supports_deadline_and_relationship_smart_views() -> None:
    parsed = parse_saved_query(
        {
            "deadline_type": ["warranty_expiration"],
            "deadlineStatuses": ["open"],
            "hasOpenDeadlines": True,
            "relationshipTypes": ["warranty_for"],
            "relationship_status": ["suggested"],
            "hasRelationships": True,
        }
    )

    assert parsed.filters.deadline_types == ("warranty_expiration",)
    assert parsed.filters.deadline_statuses == ("open",)
    assert parsed.filters.has_open_deadlines is True
    assert parsed.filters.relationship_types == ("warranty_for",)
    assert parsed.filters.relationship_statuses == ("suggested",)
    assert parsed.filters.has_relationships is True


def test_phase7_relationship_write_rejects_self_links() -> None:
    document_id = uuid4()

    try:
        RelationshipWrite.model_validate(
            {
                "fromDocumentId": str(document_id),
                "toDocumentId": str(document_id),
                "relationshipType": "related_to",
            }
        )
    except ValueError as exc:
        assert "cannot link a document to itself" in str(exc)
    else:  # pragma: no cover - the model must reject this path.
        raise AssertionError("self relationship unexpectedly validated")


def test_phase7_deadline_status_policy_tracks_review_due_soon_and_overdue() -> None:
    today = date.today()
    evidence = [{"pageNumber": 1, "sourceEngine": "system", "sourceText": "due soon"}]

    assert (
        deadline_status(due_on=today - timedelta(days=1), confidence=0.95, evidence=evidence)
        == "overdue"
    )
    assert (
        deadline_status(due_on=today + timedelta(days=10), confidence=0.95, evidence=evidence)
        == "due_soon"
    )
    assert (
        deadline_status(due_on=today + timedelta(days=45), confidence=0.95, evidence=evidence)
        == "open"
    )
    assert (
        deadline_status(due_on=today + timedelta(days=45), confidence=0.2, evidence=evidence)
        == "needs_review"
    )
    assert (
        deadline_status(due_on=today + timedelta(days=45), confidence=0.95, evidence=[])
        == "needs_review"
    )
