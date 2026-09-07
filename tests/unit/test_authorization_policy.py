from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from apps.api.structura_api.dependencies import current_principal, require_admin, require_jobs_admin
from lib.auth import AuthPrincipal
from lib.auth.authorization_policy import AuthorizationError, permits_action
from lib.automation.service import upsert_filing_rule
from lib.contacts.service import upsert_contact
from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
    document_review_access_params,
    document_write_access_params,
)
from lib.organization.manual_filing import create_folder, create_tag


def principal(role: str = "owner", scopes: tuple[str, ...] | None = None) -> AuthPrincipal:
    return AuthPrincipal(
        user_id=uuid4(),
        household_id=uuid4(),
        email="auth@example.com",
        display_name="Auth",
        auth_method="api_token" if scopes is not None else "password",
        household_role=role,
        api_token_id=uuid4() if scopes is not None else None,
        scopes=scopes or (),
    )


@pytest.mark.parametrize("role", ["owner", "admin", "member", "viewer"])
@pytest.mark.parametrize("scopes", [(), ("unknown",), ("documents:read",)])
def test_token_never_gains_write_or_admin_from_role(role, scopes) -> None:
    actor = principal(role, scopes)
    for action in ("documents:write", "documents:review", "jobs:admin", "service:admin"):
        assert not permits_action(actor, action)
    assert permits_action(actor, "documents:read") == (scopes == ("documents:read",))


@pytest.mark.parametrize("role", ["member", "viewer"])
@pytest.mark.parametrize("scopes", [("admin",), ("admin:*",), ("jobs:admin", "service:admin")])
def test_administrative_scopes_do_not_promote_members(role, scopes) -> None:
    actor = principal(role, scopes)
    for dependency in (require_admin, require_jobs_admin):
        with pytest.raises(HTTPException) as error:
            dependency(actor)
        assert error.value.status_code == 403


def test_admin_scope_is_specific_and_sessions_keep_role_authority() -> None:
    assert require_jobs_admin(principal("admin", ("jobs:admin",)))
    with pytest.raises(HTTPException):
        require_admin(principal("owner", ("jobs:admin",)))
    assert require_admin(principal("owner", ("service:admin",)))
    with pytest.raises(HTTPException):
        require_jobs_admin(principal("owner", ("service:admin",)))
    assert require_admin(principal())
    assert permits_action(principal("member"), "documents:write")
    assert not permits_action(principal("viewer", ("admin",)), "documents:write")


def test_repository_context_preserves_token_read_write_review_limits() -> None:
    actor = principal("member", ("documents:review",))
    access = DocumentAccessContext(
        household_id=actor.household_id,
        user_id=actor.user_id,
        household_role=actor.household_role,
        api_token_id=actor.api_token_id,
        scopes=actor.scopes,
    )
    assert document_read_access_params(access)[1] == actor.user_id
    assert document_review_access_params(access)[1] == actor.user_id
    assert document_write_access_params(access)[1] is None
    assert document_read_access_params(replace(access, scopes=()))[1] is None


@pytest.mark.parametrize(
    "operation", [create_folder, create_tag, upsert_contact, upsert_filing_rule]
)
@pytest.mark.parametrize("actor", [principal("viewer"), principal("owner", ("documents:read",))])
def test_direct_mutation_service_rejects_before_validation_or_database(operation, actor) -> None:
    with pytest.raises(AuthorizationError):
        operation(None, actor)


@pytest.mark.parametrize("token", ["invalid", ""])
def test_invalid_explicit_api_token_does_not_fall_back_to_cookie(monkeypatch, token) -> None:
    class Service:
        def resolve_api_token(self, _token):
            return None

        def resolve_session_token(self, _token):
            pytest.fail("An invalid explicit token must not fall back to cookie authority")

    monkeypatch.setattr("apps.api.structura_api.dependencies.AuthService", Service)
    request = Request({"type": "http", "headers": [(b"cookie", b"structura_session=valid")]})
    with pytest.raises(HTTPException) as error:
        current_principal(request, token)
    assert error.value.status_code == 401
