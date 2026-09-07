import base64
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.auth.authorization_policy import AuthorizationError
from lib.auth.request_authority import RequestCredential
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.review.line_items.history_read import line_history

from .support import (
    candidate,
    create_request,
    decide,
    expected_source,
    source,
    target,
    token_document,
)


def test_review_only_api_token_can_publish_but_intersects_current_and_captured_scopes(
    line_document,
):
    doc, _ = token_document(line_document, ["documents:review"])
    result = decide(doc, create_request(doc, candidate(doc)))
    assert result.canonical_item.selected
    request = create_request(doc, candidate(doc, "Scope revoked"), ordinal=2)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE api_tokens SET scopes=ARRAY['documents:read'] WHERE id=%s",
            (doc.credential.api_token_id,),
        )
    with pytest.raises(AuthorizationError):
        decide(doc, request)
    # A token captured with read-only scope cannot acquire authority by a later
    # scope update, even if the current database token has write permission.
    read_doc, _ = token_document(line_document, ["documents:read"])
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE api_tokens SET scopes=ARRAY['documents:write'] WHERE id=%s",
            (read_doc.credential.api_token_id,),
        )
    with pytest.raises(AuthorizationError):
        decide(read_doc, request)


def test_history_is_paginated_exact_scoped_and_survives_deleted_actor(line_document):
    doc = line_document
    first, second = candidate(doc), candidate(doc, "Replacement history")
    created = decide(doc, create_request(doc, first))
    canonical_id = created.canonical_item.id
    decide(
        doc,
        {
            "operation": "replace",
            "source": expected_source(source(doc, second)),
            "target": target(doc, canonical_id),
        },
    )
    decide(doc, {"operation": "reject_selected", "target": target(doc, canonical_id)})
    page = line_history(
        document_id=doc.document_id,
        credential=doc.credential,
        canonical_line_item_id=canonical_id,
        limit=1,
    )
    assert page.items[0].operation == "reject_selected" and page.next_cursor
    next_page = line_history(
        document_id=doc.document_id,
        credential=doc.credential,
        canonical_line_item_id=canonical_id,
        cursor=page.next_cursor,
        limit=1,
    )
    assert next_page.items[0].operation == "replace" and next_page.items[0].id != page.items[0].id
    with pytest.raises(ValueError):
        line_history(
            document_id=doc.document_id,
            credential=doc.credential,
            source_candidate_id=second,
            cursor=page.next_cursor,
        )
    auth = AuthService()
    former = auth.bootstrap_admin(
        email=f"line-temp-{uuid4()}@example.com",
        password="minimum8",
        household_name=f"Temporary line reviewer {uuid4()}",
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO household_memberships(household_id,user_id,role) VALUES(%s,%s,'admin')",
            (doc.credential.household_id, former.user_id),
        )
    session = auth.create_password_session(
        email=former.email, password="minimum8", household_id=doc.credential.household_id
    )
    principal = auth.resolve_session_token(session.token)
    assert principal is not None
    former_doc = replace(
        doc, principal=principal, credential=RequestCredential.from_principal(principal)
    )
    restored = decide(
        former_doc,
        {
            "operation": "replace",
            "source": expected_source(source(former_doc, second)),
            "target": target(former_doc, canonical_id),
        },
    )
    event_id = restored.event_id
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM users WHERE id=%s", (former.user_id,))
    entry = line_history(
        document_id=doc.document_id, credential=doc.credential, source_candidate_id=second
    ).items[0]
    assert entry.id == event_id and entry.actor_label == "Deleted reviewer"


def test_http_contract_auth_errors_and_deprecated_endpoint_fail_closed(line_document):
    doc = line_document
    token_doc, token = token_document(doc, ["documents:review"])
    item = candidate(doc)
    client = TestClient(create_app(), headers={"X-API-Token": token})
    request = create_request(token_doc, item).model_dump(mode="json", by_alias=True)
    response = client.post(f"/api/v1/documents/{doc.document_id}/line-item-decisions", json=request)
    assert response.status_code == 200, response.text
    assert response.json()["canonicalItem"]["netAmount"] == "99999999999999.9999"
    assert (
        client.post(
            f"/api/v1/documents/{doc.document_id}/line-item-decisions", json=request
        ).status_code
        == 409
    )
    assert client.get(f"/api/v1/documents/{doc.document_id}/line-item-history").status_code == 422
    for invalid in (3, {}):
        scope = f"{doc.document_id}:candidate:{item}"
        cursor = base64.urlsafe_b64encode(
            json.dumps([scope, "2026-09-07T00:00:00+00:00", invalid]).encode()
        ).decode()
        assert (
            client.get(
                f"/api/v1/documents/{doc.document_id}/line-item-history",
                params={"sourceCandidateId": str(item), "cursor": cursor},
            ).status_code
            == 422
        )
    unauthenticated = TestClient(create_app())
    assert (
        unauthenticated.get(f"/api/v1/documents/{doc.document_id}/canonical-line-items").status_code
        == 401
    )
    legacy = {
        "schemaName": "review_action",
        "schemaVersion": "v1",
        "documentId": str(doc.document_id),
        "actionType": "accept_line_item",
        "actorType": "human",
        "metadata": {"lineItemCandidateId": str(item)},
        "createdAt": "2026-09-07T00:00:00Z",
    }
    assert (
        client.post(f"/api/v1/documents/{doc.document_id}/review-actions", json=legacy).status_code
        == 409
    )


def test_http_session_review_requires_bound_csrf_and_valid_provided_origin(line_document):
    doc = line_document
    session = AuthService().create_password_session(email=doc.email, password="minimum8")
    settings = get_settings()
    headers = {
        "Cookie": f"{settings.session_cookie_name}={session.token}; "
        f"{settings.csrf_cookie_name}={session.csrf_token}",
        "X-CSRF-Token": session.csrf_token,
        "Origin": settings.web_origin,
    }
    request = create_request(doc, candidate(doc)).model_dump(mode="json", by_alias=True)
    client = TestClient(create_app())
    url = f"/api/v1/documents/{doc.document_id}/line-item-decisions"
    for origin in ("null", "https://foreign.example"):
        assert (
            client.post(url, json=request, headers={**headers, "Origin": origin}).status_code == 403
        )
    for csrf in (None, "wrong-bound-token"):
        denied_headers = {key: value for key, value in headers.items() if key != "X-CSRF-Token"}
        if csrf:
            denied_headers["X-CSRF-Token"] = csrf
        assert client.post(url, json=request, headers=denied_headers).status_code == 403
    accepted = client.post(url, json=request, headers=headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["canonicalItem"]["selected"]
