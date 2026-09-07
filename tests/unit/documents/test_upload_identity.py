from types import SimpleNamespace
from uuid import uuid4

import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api.structura_api import routes_documents
from apps.api.structura_api.dependencies import require_document_write
from lib.auth import AuthPrincipal
from lib.contracts import AcceptedJob


def test_upload_response_preserves_job_fields_and_returns_the_ingestion_document_identity(
    monkeypatch,
):
    job_id, document_id = uuid4(), uuid4()
    result = SimpleNamespace(
        accepted_job=AcceptedJob(jobId=job_id, status="queued"),
        document_id=document_id,
    )
    monkeypatch.setattr(
        routes_documents, "ingest_authenticated_document_stream", lambda *args, **kwargs: result
    )
    app = FastAPI()
    app.include_router(routes_documents.router)
    app.dependency_overrides[require_document_write] = lambda: AuthPrincipal(
        uuid4(),
        uuid4(),
        "upload@example.com",
        "Uploader",
        "password",
        session_id=uuid4(),
        csrf_token_hash="synthetic-session-binding",
    )
    actual = TestClient(app).post(
        "/api/v1/documents",
        data={"source": "web_upload"},
        files={"file": ("same.pdf", b"%PDF-1.7", "application/pdf")},
    )
    assert actual.status_code == 202
    assert actual.json() == {
        "jobId": str(job_id),
        "status": "queued",
        "documentId": str(document_id),
    }
    with open("contracts/api/openapi.yaml") as source:
        contract = yaml.safe_load(source)
    schema = contract["paths"]["/api/v1/documents"]["post"]["responses"]["202"]["content"][
        "application/json"
    ]["schema"]
    Draft202012Validator({**schema, "components": contract["components"]}).validate(actual.json())
