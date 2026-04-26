from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("psycopg")

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from workers.watched_folders.worker import scan_once


def _phase6_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    label: str,
) -> tuple[TestClient, str, uuid.UUID, uuid.UUID]:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / f"runtime-{label}"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase6-{label}-{unique}@example.com"
    password = "minimum8"
    bootstrap = AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name=f"Phase 6 {label} Admin",
        household_name=f"Phase 6 {label} {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    return client, client.cookies["structura_csrf"], bootstrap.household_id, bootstrap.user_id


def _upload_document(client: TestClient, csrf: str, title: str) -> str:
    accepted = client.post(
        "/api/v1/documents",
        headers={"X-CSRF-Token": csrf},
        data={"source": "web_upload", "suppliedTitle": title},
        files={"file": (f"{title}.pdf", b"%PDF-1.7\n%%EOF\n", "application/pdf")},
    )
    assert accepted.status_code == 202
    listed = client.get("/api/v1/documents", params={"q": title})
    assert listed.status_code == 200
    return str(listed.json()["items"][0]["id"])


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 6 automation tests.",
)
def test_phase6_contacts_document_links_rules_suggestions_and_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, csrf, _household_id, _user_id = _phase6_client(monkeypatch, tmp_path, "rules")
    unique = uuid.uuid4().hex[:8]
    document_id = _upload_document(client, csrf, f"Phase6 Aetna EOB {unique}")
    folder = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={"folderKind": "manual", "name": f"Phase6 EOBs {unique}"},
    )
    assert folder.status_code == 201

    contact = client.post(
        "/api/v1/contacts",
        headers={"X-CSRF-Token": csrf},
        json={
            "contactType": "insurer",
            "displayName": f"Aetna {unique}",
            "aliases": [f"Aetna Health {unique}"],
            "identifiers": {"payerId": f"payer-{unique}"},
        },
    )
    assert contact.status_code == 201
    assert contact.json()["aliases"] == [f"Aetna Health {unique}"]

    link = client.post(
        f"/api/v1/documents/{document_id}/contacts",
        headers={"X-CSRF-Token": csrf},
        json={
            "contactId": contact.json()["id"],
            "roleName": "payer",
            "confidence": 0.97,
            "evidence": {"source": "test"},
        },
    )
    assert link.status_code == 201

    rule = client.post(
        "/api/v1/filing-rules",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": f"Aetna EOB filing {unique}",
            "priority": 80,
            "reviewRequired": True,
            "conditions": [
                {"field": "document_family", "op": "eq", "value": "generic"},
                {"field": "contacts", "op": "contains", "value": f"Aetna {unique}"},
            ],
            "actions": [
                {"type": "add_folder", "folder_id": folder.json()["id"]},
                {"type": "add_tag", "tag": "urgent"},
            ],
        },
    )
    assert rule.status_code == 201

    dry_run = client.post(
        f"/api/v1/filing-rules/{rule.json()['id']}/dry-run",
        headers={"X-CSRF-Token": csrf},
        json={"documentIds": [document_id]},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["items"][0]["matched"] is True
    assert dry_run.json()["items"][0]["proposedActions"]

    suggest = client.post(
        f"/api/v1/filing-rules/{rule.json()['id']}/apply",
        headers={"X-CSRF-Token": csrf},
        json={"documentId": document_id},
    )
    assert suggest.status_code == 202
    assert suggest.json()["reviewRequired"] is True

    suggestions = client.get("/api/v1/filing-suggestions")
    assert suggestions.status_code == 200
    suggestion = next(
        item for item in suggestions.json()["items"] if item["documentId"] == document_id
    )

    accepted = client.post(
        f"/api/v1/filing-suggestions/{suggestion['runId']}/accept",
        headers={"X-CSRF-Token": csrf},
    )
    assert accepted.status_code == 200
    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    assert folder.json()["id"] in detail.json()["folderIds"]
    assert "urgent" in detail.json()["tags"]


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 6 automation tests.",
)
def test_phase6_watched_folder_config_and_pdf_scan_create_ingest_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, csrf, household_id, user_id = _phase6_client(monkeypatch, tmp_path, "watcher")
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    pdf = incoming / "watched.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    old_timestamp = time.time() - 120
    os.utime(pdf, (old_timestamp, old_timestamp))

    managed = client.post(
        "/api/v1/watched-folders",
        headers={"X-CSRF-Token": csrf},
        json={"path": str(tmp_path / "runtime-watcher" / "objects" / "canonical")},
    )
    assert managed.status_code == 422

    watched = client.post(
        "/api/v1/watched-folders",
        headers={"X-CSRF-Token": csrf},
        json={
            "path": str(incoming),
            "policy": {
                "allowedExtensions": [".pdf"],
                "stabilityDelaySeconds": 30,
                "processedFilePolicy": "leave",
                "recursive": False,
            },
        },
    )
    assert watched.status_code == 201

    scan = scan_once(worker_name="phase6-watch-test", household_id=household_id, user_id=user_id)
    assert scan.accepted == 1
    assert scan.rejected == 0

    listed = client.get("/api/v1/documents", params={"q": "watched"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["title"] == "Watched"
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM pipeline_jobs
                WHERE household_id = %s
                  AND queue_name = 'ingest'
                  AND payload_json->>'source' = 'watched_folder'
                """,
                (household_id,),
            )
            row = cur.fetchone()
    assert row and row["count"] >= 1


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 6 automation tests.",
)
def test_phase6_duplicate_contacts_can_be_suggested_and_merged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, csrf, _household_id, _user_id = _phase6_client(monkeypatch, tmp_path, "dedupe")
    unique = uuid.uuid4().hex[:8]
    first = _create_contact(client, csrf, f"Acme Repairs {unique}", ["Acme Repair"])
    second = _create_contact(client, csrf, f"ACME repairs {unique}", ["Acme Co"])

    suggestions = client.get("/api/v1/contact-merge-suggestions")
    assert suggestions.status_code == 200
    assert any(
        {item["sourceContactId"], item["targetContactId"]} == {first["id"], second["id"]}
        for item in suggestions.json()["items"]
    )

    merged = client.post(
        f"/api/v1/contacts/{second['id']}/merge",
        headers={"X-CSRF-Token": csrf},
        json={"targetContactId": first["id"]},
    )
    assert merged.status_code == 200
    assert "Acme Co" in merged.json()["aliases"]
    remaining = client.get("/api/v1/contacts", params={"q": unique})
    assert remaining.status_code == 200
    assert len(remaining.json()["items"]) == 1


def _create_contact(
    client: TestClient,
    csrf: str,
    name: str,
    aliases: list[str],
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/contacts",
        headers={"X-CSRF-Token": csrf},
        json={"displayName": name, "aliases": aliases},
    )
    assert response.status_code == 201
    return dict(response.json())
