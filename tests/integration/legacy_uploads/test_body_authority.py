from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from lib.auth import AuthService
from lib.auth.request_authority import RequestCredential
from lib.config import get_settings
from lib.db.connection import db_connection

from .support import partial_body_request, revoke


@pytest.mark.parametrize(
    "change", ["logout", "disabled", "membership", "role", "token", "token_scope"]
)
def test_real_partial_multipart_cannot_outlive_originating_request_authority(legacy_upload, change):
    upload = legacy_upload.with_token() if change.startswith("token") else legacy_upload
    before, files = upload.snapshot(), upload.files()

    def during_body():
        assert upload.spools and not upload.spools[0].closed
        with db_connection() as conn, conn.cursor() as cur:
            revoke(cur, upload, change)

    status, payload = partial_body_request(upload, during_body)
    assert status == 403 and payload["detail"] == "Permission denied"
    assert upload.snapshot() == before and upload.files() == files
    assert upload.spools and all(spool.closed for spool in upload.spools)


def test_real_session_replacement_during_body_cannot_substitute_its_new_credential(legacy_upload):
    upload = legacy_upload
    before, replacements = upload.snapshot(), []

    def during_body():
        client = TestClient(upload.app)
        response = client.post(
            "/api/v1/auth/session",
            headers=upload.headers(),
            json={"method": "password", "email": upload.email, "password": "minimum8"},
        )
        assert response.status_code == 201, response.text
        replacements.append(client)

    status, payload = partial_body_request(upload, during_body)
    assert status == 403 and payload["detail"] == "Permission denied"
    assert upload.snapshot() == before and upload.files() == {}
    client = replacements[0]
    settings = get_settings()
    accepted = client.post(
        "/api/v1/documents",
        headers={
            "X-CSRF-Token": client.cookies[settings.csrf_cookie_name],
            "Origin": settings.web_origin,
        },
        data={"source": "web_upload"},
        files={"file": (upload.filename, upload.content, "application/pdf")},
    )
    assert accepted.status_code == 202, accepted.text
    assert all(spool.closed for spool in upload.spools)


@pytest.mark.parametrize("credential_kind", ["session", "token"])
def test_normal_same_origin_session_and_write_token_keep_exact_upload_receipt(
    legacy_upload, credential_kind
):
    upload = legacy_upload.with_token() if credential_kind == "token" else legacy_upload
    result = upload.post()
    assert result.status_code == 202, result.text
    payload = result.json()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT d.id,j.id AS job_id,a.sha256 FROM documents d JOIN pipeline_jobs j "
            "ON j.document_id=d.id JOIN document_assets a ON a.document_id=d.id "
            "WHERE d.id=%s AND j.id=%s AND a.asset_role='original'",
            (payload["documentId"], payload["jobId"]),
        )
        row = cur.fetchone()
    assert row and str(row["id"]) == payload["documentId"] and row["sha256"] == upload.sha256
    assert upload.snapshot()["jobs"] == 4
    assert all(spool.closed for spool in upload.spools)


def test_captured_read_scope_cannot_gain_upload_authority_after_scope_expansion(legacy_upload):
    from io import BytesIO

    from lib.auth.authorization_policy import AuthorizationError
    from lib.documents.ingestion import ingest_authenticated_document_stream
    from lib.documents.ingestion_models import DocumentIngestionRequest

    upload = legacy_upload.with_token(("documents:read",))
    captured = upload.credential
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE api_tokens SET scopes=ARRAY['documents:write'] WHERE id=%s",
            (captured.api_token_id,),
        )
    current = AuthService().resolve_api_token(upload.token)
    assert current is not None
    assert RequestCredential.from_principal(current).scope_ceiling == ("documents:write",)
    before = upload.snapshot()
    with pytest.raises(AuthorizationError):
        ingest_authenticated_document_stream(
            BytesIO(upload.content),
            credential=captured,
            request=DocumentIngestionRequest(
                captured.household_id, captured.user_id, "web_upload", upload.filename
            ),
        )
    assert upload.snapshot() == before and upload.files() == {}
    assert (
        replace(upload, credential=RequestCredential.from_principal(current)).post().status_code
        == 202
    )
