from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from lib.auth.authorization_policy import AuthorizationError
from lib.auth.models import AuthPrincipal
from lib.auth.request_authority import RequestCredential
from lib.contracts.line_item_authority import LineDecisionRequest


def principal():
    return AuthPrincipal(
        uuid4(),
        uuid4(),
        "reader@example.com",
        "Reader",
        "password",
        household_role="owner",
        session_id=uuid4(),
        csrf_token_hash="bound",
    )


def create_body():
    return {
        "operation": "create",
        "source": {
            "candidateId": str(uuid4()),
            "expectedCandidateVersion": str(uuid4()),
            "expectedSourceSnapshotSha256": "a" * 64,
            "expectedCandidateDecisionRevision": None,
        },
        "target": {
            "lineItemType": "service_line",
            "ordinal": 1,
            "canonicalLineItemId": None,
            "expectedCanonicalUpdatedAt": None,
            "expectedLineDecisionRevision": None,
        },
    }


@pytest.mark.parametrize(
    "missing",
    [
        "candidateId",
        "expectedCandidateVersion",
        "expectedSourceSnapshotSha256",
        "expectedCandidateDecisionRevision",
    ],
)
def test_source_preconditions_are_required_even_when_null(missing):
    body = create_body()
    del body["source"][missing]
    with pytest.raises(ValidationError):
        TypeAdapter(LineDecisionRequest).validate_python(body)


@pytest.mark.parametrize("value", [True, 0, -1, 2147483648, "1"])
def test_target_ordinal_is_a_positive_int32_not_coercion(value):
    body = create_body()
    body["target"]["ordinal"] = value
    with pytest.raises(ValidationError):
        TypeAdapter(LineDecisionRequest).validate_python(body)


def test_explicit_replacement_has_independent_target_revision():
    body = create_body()
    body["operation"] = "replace"
    body["target"]["canonicalLineItemId"] = str(uuid4())
    body["target"]["expectedCanonicalUpdatedAt"] = "2026-09-07T12:00:00+00:00"
    parsed = TypeAdapter(LineDecisionRequest).validate_python(body)
    assert parsed.target.expected_line_decision_revision is None
    del body["target"]["expectedLineDecisionRevision"]
    with pytest.raises(ValidationError):
        TypeAdapter(LineDecisionRequest).validate_python(body)


@pytest.mark.parametrize(
    "change",
    [
        dict(session_id=None),
        dict(csrf_token_hash=None),
        dict(api_token_id=uuid4()),
        dict(household_id=None),
        dict(auth_method="operator"),
    ],
)
def test_request_origin_cannot_fall_back_to_implicit_authority(change):
    with pytest.raises(AuthorizationError):
        RequestCredential.from_principal(replace(principal(), **change))


def test_request_origin_captures_identity_without_secret():
    actor = principal()
    origin = RequestCredential.from_principal(actor)
    assert origin.session_id == actor.session_id and origin.session_csrf_bound
    assert "bound" not in repr(origin).replace("session_csrf_bound", "")
    token = replace(
        actor,
        auth_method="api_token",
        session_id=None,
        api_token_id=uuid4(),
        scopes=("documents:review", "documents:review"),
    )
    captured = RequestCredential.from_principal(token)
    assert captured.scope_ceiling == ("documents:review",)


@pytest.mark.parametrize(
    "locator",
    [
        {"sourceText": ""},
        {"sourceText": "   "},
        {"textSpan": {"start": 20, "end": 5}},
        {"textSpan": {"start": True, "end": 5}},
        {"bbox": [False, False, True, True]},
        {"bbox": [1, 1, 0, 0]},
        {"bbox": [0, 0, 5, 5]},
        {"bbox": [0, 0, float("nan"), 1]},
    ],
)
def test_line_locator_never_silently_normalizes_invalid_coordinates_or_empty_source(locator):
    from lib.contracts.line_item_authority import LineEvidenceRef

    with pytest.raises(ValidationError):
        LineEvidenceRef.model_validate({"pageNumber": 1, "sourceEngine": "validator", **locator})
