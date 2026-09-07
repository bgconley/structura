from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.structura_api.dependencies import require_document_read
from apps.api.structura_api.routes_review import router
from lib.auth import AuthPrincipal
from lib.contracts import ReviewTask
from lib.documents.access_policy import DocumentAccessContext


def test_exact_task_route_preserves_scope_and_existing_response_shape(monkeypatch):
    principal = AuthPrincipal(
        user_id=uuid4(),
        household_id=uuid4(),
        email="review@example.com",
        display_name="Reviewer",
        auth_method="api_token",
        household_role="member",
        api_token_id=uuid4(),
        scopes=("documents:read",),
    )
    task = ReviewTask.model_validate(
        {
            "id": uuid4(),
            "documentId": uuid4(),
            "taskType": "field_review",
            "status": "resolved",
            "priority": 25,
            "fieldPath": "invoice.total_amount",
            "rationale": "Reviewed against the original",
        }
    )
    read = Mock(return_value=task)
    monkeypatch.setattr("apps.api.structura_api.routes_review.get_review_task", read)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_document_read] = lambda: principal
    client = TestClient(app)

    response = client.get(f"/api/v1/review-tasks/{task.id}")
    assert response.status_code == 200
    assert response.json() == task.model_dump(mode="json", by_alias=True)
    read.assert_called_once_with(
        review_task_id=task.id,
        access=DocumentAccessContext(
            household_id=principal.household_id,
            user_id=principal.user_id,
            household_role="member",
            api_token_id=principal.api_token_id,
            scopes=("documents:read",),
        ),
    )
    read.reset_mock(return_value=True)
    read.return_value = None
    unavailable = client.get(f"/api/v1/review-tasks/{uuid4()}")
    assert unavailable.status_code == 404
    assert unavailable.json() == {"detail": "Not found"}
    read.reset_mock()
    assert client.get("/api/v1/review-tasks/not-a-uuid").status_code == 422
    read.assert_not_called()


def test_task_identity_is_not_read_before_authentication(monkeypatch):
    read = Mock(side_effect=AssertionError("Anonymous caller reached task persistence"))
    monkeypatch.setattr("apps.api.structura_api.routes_review.get_review_task", read)
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).get(f"/api/v1/review-tasks/{uuid4()}").status_code == 401
    read.assert_not_called()
