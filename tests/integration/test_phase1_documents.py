from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("psycopg")

from apps.api.structura_api import routes_documents
from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from workers.previews import PreviewError, generate_phase1_preview
from workers.previews import worker as preview_worker


def _document_by_title(client: TestClient, title: str) -> dict[str, object]:
    listed = client.get("/api/v1/documents", params={"q": title})
    assert listed.status_code == 200
    return next(item for item in listed.json()["items"] if item["title"] == title)


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 1 document tests.",
)
def test_phase1_upload_list_detail_asset_and_duplicate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase1-{unique}@example.com"
    password = "minimum8"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name="Phase 1 Admin",
        household_name=f"Phase 1 {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201

    csrf = client.cookies["structura_csrf"]
    pdf_bytes = b"%PDF-1.7\n% Structura test fixture\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    upload = client.post(
        "/api/v1/documents",
        data={"source": "web_upload", "suppliedTitle": "Phase 1 Fixture"},
        files={"file": ("phase1.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 403

    accepted = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload", "suppliedTitle": "Phase 1 Fixture"},
        files={"file": ("phase1.pdf", pdf_bytes, "application/pdf")},
    )
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued"
    item = _document_by_title(client, "Phase 1 Fixture")
    document_id = uuid.UUID(str(item["id"]))
    assert (
        preview_worker.process_next_preview_job(
            worker_name="phase1-test",
            document_id=document_id,
        )
        is True
    )

    listed = client.get("/api/v1/documents")
    assert listed.status_code == 200
    item = next(item for item in listed.json()["items"] if item["title"] == "Phase 1 Fixture")
    assert item["thumbnailUrl"].startswith("/api/v1/assets/")

    detail = client.get(f"/api/v1/documents/{item['id']}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["assets"]
    assert payload["pages"][0]["imageUrl"].startswith("/api/v1/assets/")
    assert all("filesystem://" not in str(asset) for asset in payload["assets"])

    original = next(asset for asset in payload["assets"] if asset["assetRole"] == "original")
    asset = client.get(original["assetUrl"])
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("application/pdf")
    assert asset.content == pdf_bytes

    duplicate = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload", "suppliedTitle": "Phase 1 Duplicate"},
        files={"file": ("phase1-copy.pdf", pdf_bytes, "application/pdf")},
    )
    assert duplicate.status_code == 202

    duplicate_list = client.get("/api/v1/documents", params={"q": "Phase 1 Duplicate"}).json()
    assert duplicate_list["total"] >= 1


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 1 document tests.",
)
def test_phase1_upload_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase1-validation-{unique}@example.com"
    password = "minimum8"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name="Phase 1 Validation Admin",
        household_name=f"Phase 1 Validation {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    csrf = client.cookies["structura_csrf"]

    invalid_hints = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload", "hintsJson": "{not-json"},
        files={"file": ("phase1.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert invalid_hints.status_code == 422

    invalid_mime = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload"},
        files={"file": ("phase1.txt", b"plain text", "text/plain")},
    )
    assert invalid_mime.status_code == 415

    empty = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 422


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 1 document tests.",
)
def test_phase1_upload_rolls_back_committed_object_on_job_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase1-rollback-{unique}@example.com"
    password = "minimum8"
    title = f"Phase 1 Rollback {unique}"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name="Phase 1 Rollback Admin",
        household_name=f"Phase 1 Rollback {unique}",
        must_rotate=False,
    )

    def fail_job_creation(*_args, **_kwargs):
        raise RuntimeError("injected job enqueue failure")

    monkeypatch.setattr(routes_documents, "create_job_with_cursor", fail_job_creation)
    client = TestClient(create_app(), raise_server_exceptions=False)
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201

    failed = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
        data={"source": "web_upload", "suppliedTitle": title},
        files={"file": ("rollback.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )

    assert failed.status_code == 500
    assert list((runtime_root / "objects" / "canonical").glob("**/*.blob")) == []
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM documents WHERE title = %s", (title,))
            assert cur.fetchone()["total"] == 0


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 1 document tests.",
)
def test_phase1_preview_generation_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase1-preview-{unique}@example.com"
    password = "minimum8"
    title = f"Phase 1 Preview {unique}"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name="Phase 1 Preview Admin",
        household_name=f"Phase 1 Preview {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    accepted = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
        data={"source": "web_upload", "suppliedTitle": title},
        files={"file": ("preview.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert accepted.status_code == 202
    document = _document_by_title(client, title)
    document_id = uuid.UUID(str(document["id"]))
    assert preview_worker.process_next_preview_job(
        worker_name="phase1-preview-test",
        document_id=document_id,
    )
    generate_phase1_preview(document_id)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT asset_role::text AS asset_role, count(*) AS total
                FROM document_assets
                WHERE document_id = %s
                  AND asset_role IN ('thumbnail', 'page_image')
                  AND is_current
                GROUP BY asset_role
                """,
                (document_id,),
            )
            counts = {row["asset_role"]: row["total"] for row in cur.fetchall()}
            cur.execute(
                """
                SELECT count(*) AS total
                FROM document_pages
                WHERE document_id = %s
                  AND page_number = 1
                  AND image_asset_id IS NOT NULL
                  AND thumbnail_asset_id IS NOT NULL
                """,
                (document_id,),
            )
            page_count = cur.fetchone()["total"]

    assert counts == {"page_image": 1, "thumbnail": 1}
    assert page_count == 1


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 1 document tests.",
)
def test_phase1_preview_failure_marks_retryable_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase1-preview-fail-{unique}@example.com"
    password = "minimum8"
    title = f"Phase 1 Preview Failure {unique}"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name="Phase 1 Preview Failure Admin",
        household_name=f"Phase 1 Preview Failure {unique}",
        must_rotate=False,
    )

    def fail_preview(*_args, **_kwargs) -> None:
        raise PreviewError("injected preview failure")

    monkeypatch.setattr(preview_worker, "generate_page_previews", fail_preview)
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201

    accepted = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": client.cookies["structura_csrf"]},
        data={"source": "web_upload", "suppliedTitle": title},
        files={"file": ("preview-failure.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert accepted.status_code == 202
    document = _document_by_title(client, title)
    document_id = uuid.UUID(str(document["id"]))
    assert preview_worker.process_next_preview_job(
        worker_name="phase1-preview-fail-test",
        document_id=document_id,
    )
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status::text AS status, error_json
                FROM pipeline_jobs
                WHERE document_id = %s
                  AND job_type = 'preview'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            )
            job = cur.fetchone()

    assert job["status"] == "failed"
    assert job["error_json"]["retryable"] is True
    assert job["error_json"]["suppressed"] is True
