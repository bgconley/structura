from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from lib.auth.authorization_policy import AuthorizationError
from lib.auth.request_authority import RequestCredential
from lib.documents import ingestion
from lib.documents.ingestion_models import DocumentIngestionRequest
from lib.storage import StagedObject


@pytest.mark.parametrize("mismatch", ["household", "owner", "missing"])
def test_authenticated_intake_rejects_identity_mismatch_before_staging(monkeypatch, mismatch):
    credential = RequestCredential(
        uuid4(), uuid4(), "session", uuid4(), None, session_csrf_bound=True
    )
    request = DocumentIngestionRequest(
        credential.household_id, credential.user_id, "web_upload", "a.pdf"
    )
    if mismatch == "household":
        request = replace(request, household_id=uuid4())
    elif mismatch == "owner":
        request = replace(request, owner_user_id=uuid4())
    else:
        credential = None
    storage = Mock()
    monkeypatch.setattr(ingestion, "ObjectStorage", storage)
    with pytest.raises(AuthorizationError):
        ingestion.ingest_authenticated_document_stream(
            BytesIO(b"%PDF-1.7"), request=request, credential=credential
        )
    storage.assert_not_called()


def test_staged_persistence_defensively_rejects_a_different_owner_before_io(monkeypatch):
    credential = RequestCredential(
        uuid4(), uuid4(), "session", uuid4(), None, session_csrf_bound=True
    )
    request = DocumentIngestionRequest(credential.household_id, uuid4(), "web_upload", "a.pdf")
    storage, connection = Mock(), Mock()
    monkeypatch.setattr(ingestion, "db_connection", connection)
    with pytest.raises(AuthorizationError):
        ingestion.ingest_staged_document(
            StagedObject(Path("unused-test-stage"), "a" * 64, 8),
            request=request,
            storage=storage,
            credential=credential,
        )
    assert storage.mock_calls == []
    connection.assert_not_called()
