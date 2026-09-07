from __future__ import annotations

import anyio
import httpx
import pytest

from lib.db.connection import db_connection
from lib.uploads.models import UploadAttempt
from tests.integration.uploads.test_lifecycle import rows


def run_client(upload, work):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=upload.app),
            base_url="http://test",
            headers=upload.headers(),
        ) as client:
            return await work(client)

    return anyio.run(run)


def test_authenticated_api_raw_upload_receipt_replay_and_cancel(upload):
    async def execute(client):
        metadata = upload.command()
        registered = await client.post(
            "/api/v1/uploads", json=metadata.model_dump(mode="json", by_alias=True)
        )
        assert registered.status_code == 200, registered.text
        attempt = UploadAttempt.model_validate(registered.json())
        received = await client.put(
            f"/api/v1/uploads/{attempt.upload_id}/content",
            content=b"%PDF-1.7\noriginal uploaded source",
            headers={"If-Match": str(attempt.revision)},
        )
        assert received.status_code == 200, received.text
        accepted = UploadAttempt.model_validate(received.json())
        outcome = await client.get(f"/api/v1/uploads/{attempt.upload_id}")
        assert outcome.json()["receipt"] == received.json()["receipt"]
        cancelled = await client.delete(f"/api/v1/uploads/{attempt.upload_id}")
        assert cancelled.json()["receipt"] == received.json()["receipt"]
        assert accepted.receipt.job_id is not None

    run_client(upload, execute)


def test_auth_and_csrf_fail_before_body_iterator_is_read(upload):
    async def execute(client):
        async def forbidden():
            pytest.fail("Unauthorized request consumed a body")
            yield b"never"

        for headers in ({"Cookie": "", "X-CSRF-Token": ""}, {"X-CSRF-Token": "wrong"}):
            result = await client.post("/api/v1/uploads", content=forbidden(), headers=headers)
            assert result.status_code in {401, 403}

    run_client(upload, execute)


@pytest.mark.parametrize(
    "kind", ["exact", "oversize", "wrong_signature", "wrong_length", "disconnect"]
)
def test_real_api_stream_enforces_actual_bytes_without_content_length(upload, kind):
    attempt = upload.create()

    async def execute(client):
        async def chunks():
            if kind == "wrong_signature":
                yield b"x" * attempt.declared_bytes
            else:
                yield b"%PDF-1.7\n"
                if kind == "disconnect":
                    raise httpx.ReadError("Synthetic transport disconnect")
                suffix = b"original uploaded source"
                if kind == "oversize":
                    suffix += b"overflow"
                if kind == "wrong_length":
                    suffix = suffix[:-1]
                yield suffix

        result = await client.put(
            f"/api/v1/uploads/{attempt.upload_id}/content",
            content=chunks(),
            headers={"If-Match": str(attempt.revision)},
        )
        assert (
            result.status_code
            == {
                "exact": 200,
                "oversize": 413,
                "wrong_signature": 415,
                "wrong_length": 422,
                "disconnect": 500,
            }[kind]
        ), result.text
        assert "X-Request-ID" in result.headers
        assert "Synthetic transport disconnect" not in result.text

    run_client(upload, execute)
    found = rows("SELECT receipt_json FROM upload_attempts WHERE id=%s", (attempt.upload_id,))[0]
    assert bool(found["receipt_json"]) == (kind == "exact")
    assert not list(upload.service.staging.root.glob("*.data"))
    assert not rows(
        "SELECT id FROM upload_transfers WHERE upload_id=%s AND cleanup_confirmed_at IS NULL",
        (attempt.upload_id,),
    )


@pytest.mark.parametrize("decision", ["use_existing", "keep_separate"])
def test_full_api_duplicate_decision_preserves_exact_receipt_semantics(upload, decision):
    original = upload.send(upload.create())
    held = upload.send(upload.create())

    async def execute(client):
        command = {"revision": str(held.revision), "decision": decision}
        if decision == "use_existing":
            command["documentId"] = str(original.receipt.document_id)
        response = await client.post(f"/api/v1/uploads/{held.upload_id}/decision", json=command)
        assert response.status_code == 200, response.text
        result = UploadAttempt.model_validate(response.json())
        assert result.state == ("reused" if decision == "use_existing" else "accepted")
        assert (result.receipt.document_id == original.receipt.document_id) == (
            decision == "use_existing"
        )
        assert (result.receipt.job_id is None) == (decision == "use_existing")
        recovered = await client.get(f"/api/v1/uploads/{held.upload_id}")
        assert recovered.json()["receipt"] == response.json()["receipt"]
        assert "X-Request-ID" in response.headers

    run_client(upload, execute)


def test_api_originating_credential_revoked_mid_stream_cannot_accept(upload):
    attempt = upload.create()

    async def execute(client):
        async def chunks():
            yield b"%PDF-1.7\n"
            with db_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "UPDATE sessions SET revoked_at=clock_timestamp() WHERE id=%s",
                    (upload.credential.session_id,),
                )
            yield b"original uploaded source"

        result = await client.put(
            f"/api/v1/uploads/{attempt.upload_id}/content",
            content=chunks(),
            headers={"If-Match": str(attempt.revision)},
        )
        assert result.status_code == 403

    run_client(upload, execute)
    assert not rows("SELECT id FROM documents WHERE owner_user_id=%s", (upload.credential.user_id,))
    assert not list(upload.service.staging.root.glob("*.data"))


def test_api_declared_length_mismatch_is_rejected_before_bytes(upload):
    attempt = upload.create()

    async def execute(client):
        async def forbidden():
            pytest.fail("Mismatched length was consumed")
            yield b"never"

        result = await client.put(
            f"/api/v1/uploads/{attempt.upload_id}/content",
            content=forbidden(),
            headers={"If-Match": str(attempt.revision), "Content-Length": "1"},
        )
        assert result.status_code == 422

    run_client(upload, execute)
