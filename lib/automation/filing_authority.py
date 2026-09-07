"""Synchronous filing entry boundary with the automation service's public errors."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from lib.auth import AuthPrincipal
from lib.automation.errors import AutomationError
from lib.organization.authority_repository import organization_mutation
from lib.organization.policy import OrganizationError


@contextmanager
def filing_mutation(cur: Any, principal: AuthPrincipal) -> Iterator[None]:
    try:
        with organization_mutation(cur, principal):
            yield
    except OrganizationError as exc:
        raise AutomationError(exc.status_code, exc.detail) from exc
