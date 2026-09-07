from dataclasses import replace
from uuid import uuid4

import pytest

from lib.auth import AuthPrincipal
from lib.document_processing.errors import ProcessingError
from lib.document_processing.request_origin import ProcessingOrigin


def principal(**changes):
    return AuthPrincipal(
        **{
            "user_id": uuid4(),
            "household_id": uuid4(),
            "email": "test@example.com",
            "display_name": "Test",
            "auth_method": "password",
            "household_role": "owner",
            "session_id": uuid4(),
            **changes,
        }
    )


def test_explicit_session_origin_has_no_token_ceiling():
    actor = principal()
    origin = ProcessingOrigin.from_principal(actor)
    assert (origin.user_id, origin.household_id, origin.session_id) == (
        actor.user_id,
        actor.household_id,
        actor.session_id,
    )
    assert origin.kind == "session" and origin.scope_ceiling == ()


@pytest.mark.parametrize("scopes", [("documents:write",), ("admin",), ("admin:*",)])
def test_explicit_token_origin_uses_shared_scope_policy(scopes):
    actor = principal(auth_method="api_token", session_id=None, api_token_id=uuid4(), scopes=scopes)
    origin = ProcessingOrigin.from_principal(actor)
    assert origin.kind == "api_token" and origin.scope_ceiling == scopes


@pytest.mark.parametrize(
    "scopes", [(), ("documents:read",), ("documents:review",), ("jobs:admin",), ("service:admin",)]
)
def test_administrator_read_review_or_unrelated_token_is_not_a_write_origin(scopes):
    with pytest.raises(ProcessingError):
        ProcessingOrigin.from_principal(
            principal(auth_method="api_token", session_id=None, api_token_id=uuid4(), scopes=scopes)
        )


@pytest.mark.parametrize(
    "change",
    [
        {"session_id": None},
        {"household_id": None},
        {"api_token_id": uuid4()},
        {"auth_method": "operator"},
        {"auth_method": "api_token"},
    ],
)
def test_missing_or_ambiguous_origin_never_becomes_system_authority(change):
    with pytest.raises(ProcessingError):
        ProcessingOrigin.from_principal(replace(principal(), **change))
