"""Real legacy API requests, isolated persistence snapshots and credential actors."""

import asyncio
import json
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.auth import AuthService, hash_secret
from lib.auth.models import CreatedSession
from lib.auth.request_authority import RequestCredential
from lib.config import get_settings
from lib.db.connection import db_connection


@dataclass(frozen=True)
class LegacyUpload:
    app: FastAPI
    session: CreatedSession
    credential: RequestCredential
    email: str
    filename: str
    content: bytes
    runtime: Path
    spools: list
    token: str | None = None

    @property
    def sha256(self):
        return sha256(self.content).hexdigest()

    def headers(self):
        if self.token is not None:
            return {"X-API-Token": self.token}
        settings = get_settings()
        return {
            "Cookie": f"{settings.session_cookie_name}={self.session.token}; "
            f"{settings.csrf_cookie_name}={self.session.csrf_token}",
            "X-CSRF-Token": self.session.csrf_token,
            "Origin": settings.web_origin,
        }

    def post(self):
        return TestClient(self.app).post(
            "/api/v1/documents",
            headers=self.headers(),
            data={"source": "web_upload"},
            files={"file": (self.filename, self.content, "application/pdf")},
        )

    def with_token(self, scopes=("documents:write",)):
        token = uuid4().hex
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO api_tokens(user_id,household_id,label,token_hash,scopes) "
                "VALUES(%s,%s,'Legacy upload',%s,%s)",
                (
                    self.credential.user_id,
                    self.credential.household_id,
                    hash_secret(token),
                    list(scopes),
                ),
            )
        principal = AuthService().resolve_api_token(token)
        assert principal is not None
        return replace(self, credential=RequestCredential.from_principal(principal), token=token)

    def snapshot(self):
        with db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT
                (SELECT count(*) FROM documents WHERE household_id=%s) AS documents,
                (SELECT count(*) FROM document_assets a JOIN documents d ON d.id=a.document_id
                  WHERE d.household_id=%s) AS assets,
                (SELECT count(*) FROM pipeline_jobs WHERE household_id=%s) AS jobs,
                (SELECT count(*) FROM ingest_batches WHERE label=%s) AS batches""",
                (self.credential.household_id,) * 3 + (f"web_upload:{self.filename}",),
            )
            return cur.fetchone()

    def files(self):
        return {
            str(path.relative_to(self.runtime)): path.read_bytes()
            for path in self.runtime.rglob("*")
            if path.is_file()
        }


def revoke(cur, upload, kind):
    credential = upload.credential
    if kind in {"logout", "session_row"}:
        cur.execute(
            "UPDATE sessions SET revoked_at=clock_timestamp() WHERE id=%s", (credential.session_id,)
        )
    elif kind == "disabled":
        cur.execute("UPDATE users SET is_disabled=true WHERE id=%s", (credential.user_id,))
    elif kind == "membership":
        cur.execute(
            "DELETE FROM household_memberships WHERE household_id=%s AND user_id=%s",
            (credential.household_id, credential.user_id),
        )
    elif kind == "role":
        cur.execute(
            "UPDATE household_memberships SET role='viewer' WHERE household_id=%s AND user_id=%s",
            (credential.household_id, credential.user_id),
        )
    elif kind == "token_scope":
        cur.execute(
            "UPDATE api_tokens SET scopes=ARRAY['documents:read'] WHERE id=%s",
            (credential.api_token_id,),
        )
    elif kind in {"token", "token_row"}:
        cur.execute(
            "UPDATE api_tokens SET revoked_at=clock_timestamp() WHERE id=%s",
            (credential.api_token_id,),
        )
    else:
        raise AssertionError("Unknown credential fixture change")
    assert cur.rowcount == 1


def partial_body_request(upload, during_body):
    """No auth/intake mock: the independent mutation happens between actual file bytes."""
    body = (
        b'--legacy-boundary\r\nContent-Disposition: form-data; name="source"\r\n\r\nweb_upload\r\n'
        + b'--legacy-boundary\r\nContent-Disposition: form-data; name="file"; '
        + f'filename="{upload.filename}"'.encode()
        + b"\r\nContent-Type: application/pdf\r\n\r\n"
        + upload.content
        + b"\r\n--legacy-boundary--\r\n"
    )
    cut = body.index(b"%PDF") + 7

    async def run():
        sent, calls = [], 0

        async def receive():
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"type": "http.request", "body": body[:cut], "more_body": True}
            if calls == 2:
                await asyncio.to_thread(during_body)
                return {"type": "http.request", "body": body[cut:], "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        await upload.app(
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
                "headers": [(b"content-type", b"multipart/form-data; boundary=legacy-boundary")]
                + [
                    (key.lower().encode(), value.encode())
                    for key, value in upload.headers().items()
                ],
                "server": ("testserver", 80),
                "client": ("127.0.0.1", 1234),
            },
            receive,
            send,
        )
        assert calls >= 2
        status = next(item["status"] for item in sent if item["type"] == "http.response.start")
        payload = json.loads(b"".join(item.get("body", b"") for item in sent))
        return status, payload

    return asyncio.run(run())
