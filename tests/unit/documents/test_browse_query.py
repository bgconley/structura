from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api.structura_api import routes_documents
from apps.api.structura_api.dependencies import require_document_read
from lib.auth import AuthPrincipal
from lib.contracts import DocumentBrowseCounts, DocumentListResponse, DocumentSummary
from lib.documents.access_policy import DocumentAccessContext
from lib.documents.browse_query import (
    MAX_BROWSE_OFFSET,
    DocumentSort,
    InboxState,
    validate_browse_window,
)
from lib.documents.list_repository import (
    DocumentListFilters,
    _document_list_count_sql,
    _document_list_select_sql,
)


@pytest.fixture
def browse_client(monkeypatch):
    calls = []
    principal = AuthPrincipal(uuid4(), uuid4(), "browse@example.com", "Reader", "password")

    def browse(filters):
        calls.append(filters)
        return DocumentListResponse(
            items=[],
            total=0,
            limit=filters.limit,
            offset=filters.offset,
            corpus_total=12,
            observed_at=datetime(2026, 9, 7, tzinfo=UTC),
            counts=DocumentBrowseCounts(all=3, needs_review=2),
        )

    monkeypatch.setattr(routes_documents, "list_document_summaries", browse)
    app = FastAPI()
    app.include_router(routes_documents.router)
    app.dependency_overrides[require_document_read] = lambda: principal
    return TestClient(app), calls, principal


@pytest.mark.parametrize(
    "params",
    [
        {"inboxState": "needs_review; DROP TABLE documents"},
        {"sort": "d.title"},
        {"offset": -1},
        {"offset": MAX_BROWSE_OFFSET + 1},
        {"offset": "1.5"},
        {"limit": 0},
        {"limit": 201},
    ],
)
def test_invalid_options_never_reach_document_repository(browse_client, params):
    client, calls, _ = browse_client
    assert client.get("/api/v1/documents", params=params).status_code == 422
    assert not calls


def test_browse_options_and_live_access_context_reach_repository(browse_client):
    client, calls, principal = browse_client
    folder_id = uuid4()
    response = client.get(
        "/api/v1/documents",
        params={
            "q": "  invoice  ",
            "family": "invoice",
            "reviewStatus": "needs_review",
            "folderId": str(folder_id),
            "inboxState": "unfiled",
            "sort": "document_date_asc",
            "limit": 25,
            "offset": 50,
        },
    )
    assert response.status_code == 200
    query = calls[0]
    assert query.access.user_id == principal.user_id
    assert query.access.household_id == principal.household_id
    assert (query.query_text, query.family, query.review_status) == (
        "invoice",
        "invoice",
        "needs_review",
    )
    assert (query.folder_id, query.inbox_state, query.sort) == (
        folder_id,
        InboxState.UNFILED,
        DocumentSort.DOCUMENT_DATE_ASC,
    )
    payload = response.json()
    assert (payload["limit"], payload["offset"], payload["corpusTotal"]) == (25, 50, 12)
    assert payload["observedAt"] == "2026-09-07T00:00:00Z"
    assert payload["counts"]["needsReview"] == 2
    assert payload["counts"]["lowConfidence"] == 0


def test_legacy_document_list_defaults_are_preserved(browse_client):
    client, calls, _ = browse_client
    assert client.get("/api/v1/documents").status_code == 200
    query = calls[0]
    assert (query.limit, query.offset, query.inbox_state, query.sort) == (
        50,
        0,
        InboxState.ALL,
        DocumentSort.UPLOADED_DESC,
    )


@pytest.mark.parametrize("limit,offset", [(True, 0), (50, False), (1, -1), (201, 0)])
def test_repository_pagination_boundary_rejects_invalid_direct_values(limit, offset):
    with pytest.raises(ValueError):
        validate_browse_window(limit, offset)


def test_document_browse_contract_matches_runtime_options_and_response_properties():
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text())
    operation = contract["paths"]["/api/v1/documents"]["get"]
    parameters = {item["name"]: item["schema"] for item in operation["parameters"]}
    assert set(parameters["inboxState"]["enum"]) == set(InboxState)
    assert set(parameters["sort"]["enum"]) == set(DocumentSort)
    assert parameters["offset"]["maximum"] == MAX_BROWSE_OFFSET
    for model in (DocumentBrowseCounts, DocumentListResponse):
        documented = contract["components"]["schemas"][model.__name__]
        assert set(documented["properties"]) == set(model.model_json_schema()["properties"])


def test_browse_sql_composition_preserves_json_literals_and_bind_parameters():
    where_sql = "document_is_readable(d.id, %s, %s, %s)"
    counts = _document_list_count_sql(where_sql).as_string()
    assert "'{}'::jsonb" in counts
    assert counts.count("%s") == 6  # Authorized counterpart, then authorized document.
    for state in InboxState:
        for sort in DocumentSort:
            filters = DocumentListFilters(
                DocumentAccessContext(uuid4(), uuid4()), inbox_state=state, sort=sort
            )
            page = _document_list_select_sql(where_sql, filters).as_string()
            assert "'{}'::jsonb" in page
            assert page.count("%s") == 11  # Related count, counterpart, document, page bounds.
            assert "NULLS LAST, d.id " in page


def test_populated_list_response_validates_against_the_published_openapi_contract(
    browse_client,
    monkeypatch,
):
    client, _, _ = browse_client
    instant = datetime(2026, 9, 7, tzinfo=UTC)
    document = DocumentSummary(
        id=uuid4(),
        title="Unclassified original",
        family="generic",
        lifecycleState="inbox",
        reviewStatus="unreviewed",
        createdAt=instant,
    )
    response = DocumentListResponse(
        items=[document],
        total=1,
        limit=50,
        offset=0,
        corpusTotal=1,
        observedAt=instant,
        counts=DocumentBrowseCounts(all=1, unfiled=1, awaitingClassification=1),
    )
    monkeypatch.setattr(routes_documents, "list_document_summaries", lambda filters: response)
    actual = client.get("/api/v1/documents")
    assert actual.status_code == 200
    payload = actual.json()
    assert payload["items"][0]["createdAt"] == "2026-09-07T00:00:00Z"
    for field in (
        "documentDate",
        "amountTotal",
        "counterpartyDisplay",
        "thumbnailUrl",
        "qualitySummary",
    ):
        assert payload["items"][0][field] is None
    contract = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text())
    Draft202012Validator(
        {
            "$ref": "#/components/schemas/DocumentListResponse",
            "components": contract["components"],
        }
    ).validate(payload)
