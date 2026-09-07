from __future__ import annotations

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.structura_api.dependencies import require_document_review
from apps.api.structura_api.routes_review import router
from lib.auth import AuthPrincipal
from lib.review.correction_values import CorrectionValueError, validate_correction_value


@pytest.mark.parametrize(
    ("value_type", "value", "currency"),
    [
        ("money", {"amount": "garbage", "currency": "USD"}, "USD"),
        ("money", {"amount": "1,25", "currency": "USD"}, "USD"),
        ("money", {"amount": 1, "currency": "EUR"}, "USD"),
        ("money", {"amount": 1, "currency": "usd"}, None),
        ("money", {"amount": 1, "currency": "USD", "extra": 2}, None),
        ("money", 1, None),
        ("number", "12tail", None),
        ("number", True, None),
        ("number", None, None),
        ("number", float("nan"), None),
        ("number", float("inf"), None),
        ("number", -float("inf"), None),
        ("number", 1e14, None),
        ("number", 1.23456, None),
        ("number", 1e-8, None),
        ("integer", 12.9, None),
        ("integer", "12", None),
        ("integer", True, None),
        ("integer", 2**63, None),
        ("boolean", "false", None),
        ("boolean", "perhaps", None),
        ("boolean", 0, None),
        ("string", None, None),
        ("unsupported", 1, None),
    ],
)
def test_invalid_corrections_are_rejected(value_type, value, currency) -> None:
    with pytest.raises(CorrectionValueError):
        validate_correction_value(value_type, value, currency)


@pytest.mark.parametrize(
    ("value_type", "value", "currency"),
    [
        ("money", {"amount": 0, "currency": "USD"}, "USD"),
        ("money", {"amount": -12.3456, "currency": "EUR"}, None),
        ("money", 21.5, "USD"),
        ("number", 0, None),
        ("number", -0.0001, None),
        ("integer", 0, None),
        ("integer", -(2**63), None),
        ("boolean", False, None),
        ("boolean", True, None),
        ("string", "Original text", None),
    ],
)
def test_valid_corrections_preserve_values(value_type, value, currency) -> None:
    validate_correction_value(value_type, value, currency)


@pytest.mark.parametrize("endpoint", ["canonical-fields", "review-actions"])
@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        ("money", {"amount": "private-invalid-amount", "currency": "USD"}),
        ("number", "1,200.00"),
        ("number", 1.23456),
        ("integer", 3.5),
        ("boolean", "false"),
    ],
)
def test_both_api_paths_reject_invalid_values_before_any_side_effect(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, value_type: str, value: object
) -> None:
    document_id = uuid4()
    principal = AuthPrincipal(
        user_id=uuid4(),
        household_id=uuid4(),
        email="review@example.com",
        display_name="Reviewer",
        auth_method="session",
        household_role="admin",
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_document_review] = lambda: principal
    write = Mock(side_effect=AssertionError("Invalid correction reached persistence"))
    projection = Mock(side_effect=AssertionError("Invalid correction refreshed projection"))
    monkeypatch.setattr("lib.review.repository.upsert_human_canonical_field", write)
    monkeypatch.setattr("lib.review.service.refresh_projection_and_enqueue_embedding", projection)
    evidence = [{"pageNumber": 1, "sourceEngine": "human", "sourceText": "Original amount"}]
    payload = (
        {
            "fieldPath": "invoice.total_amount",
            "valueType": value_type,
            "value": value,
            "currency": "USD" if value_type == "money" else None,
            "sourceKind": "human",
            "evidence": evidence,
        }
        if endpoint == "canonical-fields"
        else {
            "documentId": str(document_id),
            "actionType": "correct_field",
            "fieldPath": "invoice.total_amount",
            "newValue": value,
            "evidenceContext": evidence,
            "metadata": {
                "valueType": value_type,
                "currency": "USD" if value_type == "money" else None,
            },
        }
    )
    with TestClient(app) as client:
        response = client.post(f"/api/v1/documents/{document_id}/{endpoint}", json=payload)
    assert response.status_code == 422
    assert "private-invalid-amount" not in response.text
    write.assert_not_called()
    projection.assert_not_called()
