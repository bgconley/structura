import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from lib.auth import AuthService
from lib.auth.models import AuthPrincipal
from lib.auth.request_authority import RequestCredential
from lib.config import get_settings
from lib.db.connection import db_connection


@dataclass(frozen=True)
class ReviewDocument:
    document_id: UUID
    principal: AuthPrincipal
    credential: RequestCredential
    email: str


@pytest.fixture
def line_document(monkeypatch):
    url = os.environ.get("STRUCTURA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires an isolated migrated database.")
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_EMBEDDING_TEXT_ENABLED", "true")
    get_settings.cache_clear()
    auth = AuthService()
    owner = auth.bootstrap_admin(
        email=f"line-authority-{uuid4()}@example.com",
        password="minimum8",
        household_name=f"Line authority {uuid4()}",
    )
    session = auth.create_password_session(email=owner.email, password="minimum8")
    principal = auth.resolve_session_token(session.token)
    assert principal is not None
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO "
            "documents(title,ingestion_source,household_id,owner_user_id,original_sha256)"
            "VALUES('Line review','web_upload',%s,%s,%s) RETURNING id",
            (owner.household_id, owner.user_id, "a" * 64),
        )
        document_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO document_assets(document_id,asset_role,uri,sha256,mime_type) "
            "VALUES(%s,'original','/isolated/line-fixture.pdf',%s,'application/pdf')",
            (document_id, "a" * 64),
        )
        cur.execute(
            "INSERT INTO document_pages(document_id,page_number) VALUES(%s,1)", (document_id,)
        )
        cur.execute(
            "INSERT INTO document_chunks(document_id,chunk_index,text_content) "
            "VALUES(%s,1,'Source page')",
            (document_id,),
        )
    yield ReviewDocument(
        document_id, principal, RequestCredential.from_principal(principal), owner.email
    )
    get_settings.cache_clear()
