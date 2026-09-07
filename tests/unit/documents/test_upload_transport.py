"""Exercise the actual multipart route with controlled ASGI receive events."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from starlette import formparsers

from apps.api.structura_api import document_upload_form, routes_documents
from apps.api.structura_api.dependencies import current_principal, require_document_write
from apps.api.structura_api.error_handlers import install_error_handling
from lib.auth import AuthPrincipal
from lib.contracts import AcceptedJob


def multipart(content=b"%PDF-1.7", fields=(("source", "web_upload"),)):
    data = b""
    for name, value in fields:
        data += (
            f'--test-boundary\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    return data + (
        b'--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="one.pdf"'
        b"\r\nContent-Type: application/pdf\r\n\r\n" + content + b"\r\n--test-boundary--\r\n"
    )


async def request(app, chunks, *, headers=None, terminal=None):
    sent, consumed = [], []
    remaining = iter(chunks)

    async def receive():
        chunk = next(remaining, None)
        if chunk is None:
            if terminal is not None:
                return await terminal()
            return {"type": "http.request", "body": b"", "more_body": False}
        consumed.append(chunk)
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/documents",
            "raw_path": b"/api/v1/documents",
            "query_string": b"",
            "root_path": "",
            "headers": headers
            if headers is not None
            else [(b"content-type", b"multipart/form-data; boundary=test-boundary")],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 1234),
        },
        receive,
        send,
    )
    return next(
        message["status"] for message in sent if message["type"] == "http.response.start"
    ), consumed


@pytest.fixture
def transport(monkeypatch):
    spools, accepted = [], []
    original = formparsers.SpooledTemporaryFile

    def spool(*args, **kwargs):
        result = original(*args, **kwargs)
        spools.append(result)
        return result

    def accept(stream, *, request):
        accepted.append((stream.read(), request))
        return SimpleNamespace(
            accepted_job=AcceptedJob(jobId=uuid4(), status="queued"), document_id=uuid4()
        )

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", spool)
    monkeypatch.setattr(
        routes_documents, "get_settings", lambda: SimpleNamespace(max_upload_bytes=64)
    )
    monkeypatch.setattr(routes_documents, "ingest_document_stream", accept)
    app = FastAPI()
    app.include_router(routes_documents.router)
    install_error_handling(app)
    return app, spools, accepted


def authorize(app):
    app.dependency_overrides[require_document_write] = lambda: AuthPrincipal(
        uuid4(), uuid4(), "synthetic@example.com", "Synthetic", "password"
    )


@pytest.mark.parametrize("denial", ["anonymous", "read_token", "missing_csrf"])
def test_authorization_finishes_without_consuming_any_upload_bytes(transport, denial):
    app, spools, accepted = transport
    if denial != "anonymous":
        app.dependency_overrides[current_principal] = lambda: AuthPrincipal(
            uuid4(),
            uuid4(),
            "synthetic@example.com",
            "Synthetic",
            "password",
            api_token_id=uuid4() if denial == "read_token" else None,
            scopes=("documents:read",),
        )
    status, consumed = asyncio.run(request(app, [b"malformed private upload bytes"]))
    assert status == (401 if denial == "anonymous" else 403)
    assert consumed == spools == accepted == []


@pytest.mark.parametrize("length_header", [False, True])
def test_exact_file_limit_accepts_existing_fields_and_closes_spool(transport, length_header):
    app, spools, accepted = transport
    authorize(app)
    content = b"%PDF-" + b"x" * 59
    body = multipart(
        content,
        (
            ("source", "web_upload"),
            ("suppliedTitle", "Synthetic"),
            ("hintsJson", '{"documentType":"invoice"}'),
        ),
    )
    headers = [(b"content-type", b"multipart/form-data; boundary=test-boundary")]
    if length_header:
        headers.append((b"content-length", str(len(body)).encode()))
    assert asyncio.run(request(app, [body], headers=headers))[0] == 202
    assert accepted[0][0] == content
    assert accepted[0][1].supplied_title == "Synthetic"
    assert accepted[0][1].hints == {"documentType": "invoice"}
    assert len(spools) == 1 and spools[0].closed


@pytest.mark.parametrize(
    "body,status",
    [
        (multipart(b"x" * 65), 413),
        (multipart()[:-10], 400),
        (multipart(fields=()), 422),
        (multipart(fields=(("source", "web_upload"), ("source", "api_upload"))), 422),
        (multipart(fields=(("source", "x" * (16 * 1024 + 1)),)), 413),
        (
            multipart().replace(b'filename="one.pdf"', b'filename="' + b"x" * (16 * 1024) + b'"'),
            413,
        ),
        (multipart() + b"x" * (64 * 1024), 413),
    ],
)
def test_actual_stream_and_multipart_structure_fail_closed(transport, body, status):
    app, spools, accepted = transport
    authorize(app)
    assert (
        asyncio.run(request(app, [body[i : i + 53] for i in range(0, len(body), 53)]))[0] == status
    )
    assert accepted == []
    assert all(spool.closed for spool in spools)


@pytest.mark.parametrize("lengths", [[b"-1"], [b"1,1"], [b"1", b"1"], [b"99999999999999999999999"]])
def test_invalid_or_oversize_declared_length_never_reads_body(transport, lengths):
    app, spools, accepted = transport
    authorize(app)
    status, consumed = asyncio.run(
        request(
            app,
            [multipart()],
            headers=[
                (b"content-type", b"multipart/form-data; boundary=test-boundary"),
                *((b"content-length", length) for length in lengths),
            ],
        )
    )
    assert status in {400, 413}
    assert consumed == spools == accepted == []


@pytest.mark.parametrize("difference", [-1, 1])
def test_declared_length_must_equal_actual_body(transport, difference):
    app, spools, accepted = transport
    authorize(app)
    body = multipart()
    assert (
        asyncio.run(
            request(
                app,
                [body],
                headers=[
                    (b"content-type", b"multipart/form-data; boundary=test-boundary"),
                    (b"content-length", str(len(body) + difference).encode()),
                ],
            )
        )[0]
        == 400
    )
    assert accepted == []
    assert all(spool.closed for spool in spools)


@pytest.mark.parametrize("failure", ["disconnect", "idle", "deadline", "cancel"])
def test_interrupted_partial_file_always_closes_owned_spool(transport, monkeypatch, failure):
    app, spools, accepted = transport
    authorize(app)
    monkeypatch.setattr(document_upload_form, "TRANSFER_IDLE_SECONDS", 0.01)
    if failure == "deadline":
        monkeypatch.setattr(document_upload_form, "TRANSFER_IDLE_SECONDS", 1)
        monkeypatch.setattr(document_upload_form, "TRANSFER_DEADLINE_SECONDS", 0.01)

    async def terminal():
        if failure == "cancel":
            raise asyncio.CancelledError()
        if failure in {"idle", "deadline"}:
            await asyncio.sleep(1)
        return {"type": "http.disconnect"}

    call = request(app, [multipart().split(b"%PDF")[0] + b"%PDF"], terminal=terminal)
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(call)
    else:
        assert asyncio.run(call)[0] == (408 if failure in {"idle", "deadline"} else 400)
    assert accepted == []
    assert len(spools) == 1 and spools[0].closed


def test_file_rolled_to_disk_closes_after_intake_failure(transport, monkeypatch):
    app, spools, accepted = transport
    authorize(app)
    monkeypatch.setattr(
        routes_documents, "get_settings", lambda: SimpleNamespace(max_upload_bytes=2 * 1024 * 1024)
    )

    def fail(stream, **kwargs):
        assert stream._rolled
        assert not stream.closed
        raise RuntimeError("Synthetic intake failure")

    monkeypatch.setattr(routes_documents, "ingest_document_stream", fail)
    body = multipart(b"%PDF-" + b"x" * (1100 * 1024))
    assert asyncio.run(request(app, [body]))[0] == 500
    assert accepted == []
    assert len(spools) == 1 and spools[0].closed
