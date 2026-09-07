from concurrent.futures import ThreadPoolExecutor

import pytest

from lib.auth import AuthService
from lib.db.connection import db_connection
from lib.document_processing.errors import ProcessingAuthorityLost

from .authority_cases import revoke, token_request
from .test_parse_execution import FixtureClient, execute
from .test_parse_execution import source_execution as source_execution


@pytest.mark.parametrize("change", ["disabled", "token_revoked"])
def test_revoked_request_does_not_read_source_or_invoke_first_model(
    source_execution, change, monkeypatch
):
    processing, storage, deployment = source_execution
    request = token_request(processing) if change.startswith("token_") else processing
    run, client = request.start(), FixtureClient()
    claimed = request.claim()
    with db_connection() as conn, conn.cursor() as cur:
        revoke(cur, request, change)
    monkeypatch.setattr(
        type(storage), "path_for_uri", lambda *_: pytest.fail("Revoked source bytes were accessed")
    )
    with request.scope(claimed), pytest.raises(ProcessingAuthorityLost):
        execute(run, storage, deployment, client)
    assert client.calls == []


@pytest.mark.parametrize("change", ["disabled", "token_revoked"])
def test_independent_revocation_during_model_call_denies_checkpoint_and_next_call(
    source_execution, change
):
    processing, storage, deployment = source_execution
    request = token_request(processing) if change.startswith("token_") else processing
    run = request.start()
    claimed = request.claim()

    def revoke_during_model():
        with db_connection() as conn, conn.cursor() as cur:
            revoke(cur, request, change)

    with ThreadPoolExecutor(max_workers=1) as pool:
        client = FixtureClient(
            after_generate=lambda: pool.submit(revoke_during_model).result(timeout=5)
        )
        with request.scope(claimed), pytest.raises(ProcessingAuthorityLost):
            execute(run, storage, deployment, client)
    assert client.calls == [1]
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id=%s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 0


def test_browser_logout_during_model_does_not_cancel_durable_ingestion(source_execution):
    processing, storage, deployment = source_execution
    run, claimed = processing.start(), processing.claim()
    client = FixtureClient(
        after_generate=lambda: AuthService().revoke_authenticated_session(processing.principal)
    )
    with processing.scope(claimed):
        result = execute(run, storage, deployment, client)
    assert client.calls == [1, 2] and result.page_count == 2
