"""Real isolated SQL upload actors; no model service or production namespace."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import uuid4

import anyio
import pytest
from fastapi import FastAPI

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.auth.request_authority import RequestCredential
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.storage import ObjectStorage
from lib.uploads.cleanup import clean_transfer
from lib.uploads.models import UploadCreate
from lib.uploads.operation_repository import create_attempt
from lib.uploads.policy import UploadPolicy
from lib.uploads.service import UploadService


@dataclass
class UploadHarness:
    service: UploadService
    credential: RequestCredential
    session: object
    principal: object
    email: str
    app: FastAPI

    def command(self, data=b"%PDF-1.7\noriginal uploaded source", **updates):
        return UploadCreate.model_validate(
            {
                "operation_id": uuid4(),
                "client_batch_id": uuid4(),
                "filename": "original.pdf",
                "declared_bytes": len(data),
                **updates,
            }
        )

    def create(self, data=b"%PDF-1.7\noriginal uploaded source", **updates):
        return create_attempt(self.command(data, **updates), self.credential, self.service.policy)

    def send(self, attempt, data=b"%PDF-1.7\noriginal uploaded source", **kwargs):
        async def body():
            yield data

        async def execute():
            return await self.service.receive(
                attempt.upload_id, attempt.revision, self.credential, body(), **kwargs
            )

        return anyio.run(execute)

    def headers(self):
        settings = get_settings()
        return {
            "Cookie": f"{settings.session_cookie_name}={self.session.token}; "
            f"{settings.csrf_cookie_name}={self.session.csrf_token}",
            "X-CSRF-Token": self.session.csrf_token,
            "Origin": settings.web_origin,
        }


@pytest.fixture
def upload(monkeypatch, tmp_path):
    url = os.environ.get("STRUCTURA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires an isolated PostgreSQL database migrated through104.")
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    auth = AuthService()
    owner = auth.bootstrap_admin(
        email=f"upload-{uuid4()}@example.com",
        password="minimum8",
        household_name=f"Upload {uuid4()}",
    )
    session = auth.create_password_session(email=owner.email, password="minimum8")
    principal = auth.resolve_session_token(session.token)
    assert principal is not None
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    service = UploadService(storage, UploadPolicy())
    # Actual auth/CSRF dependencies remain wired; only the storage/config instance is injected.
    monkeypatch.setattr(
        "apps.api.structura_api.routes_uploads.UploadService", lambda **_kwargs: service
    )
    app = create_app()

    yield UploadHarness(
        service, RequestCredential.from_principal(principal), session, principal, owner.email, app
    )
    # Test teardown retains tombstones and uses actual locked byte cleanup.
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE upload_transfers SET revoked_at=COALESCE(revoked_at,clock_timestamp()),
            cleanup_expires_at=CASE WHEN cleanup_token IS NOT NULL
                THEN clock_timestamp()-interval '1 second' ELSE NULL END
            WHERE upload_id IN (SELECT id FROM upload_attempts WHERE household_id=%s)
            AND cleanup_confirmed_at IS NULL RETURNING id""",
            (owner.household_id,),
        )
        remaining = [row["id"] for row in cur.fetchall()]
    for transfer_id in remaining:
        clean_transfer(service.staging, transfer_id, service.policy)
    get_settings.cache_clear()
