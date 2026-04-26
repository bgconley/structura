from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("psycopg")

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.auth.service import hash_password
from lib.config import get_settings
from lib.db.connection import db_connection


def _phase2_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    label: str,
) -> tuple[TestClient, str]:
    database_url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / f"runtime-{label}"))
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()

    unique = uuid.uuid4().hex[:12]
    email = f"phase2-{label}-{unique}@example.com"
    password = "minimum8"
    AuthService().bootstrap_admin(
        email=email,
        password=password,
        display_name=f"Phase 2 {label} Admin",
        household_name=f"Phase 2 {label} {unique}",
        must_rotate=False,
    )
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": email, "password": password},
    )
    assert login.status_code == 201
    return client, client.cookies["structura_csrf"]


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


def _add_household_user(
    *,
    household_id: str,
    email: str,
    password: str,
    role: str = "viewer",
) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (email, display_name)
                VALUES (%s, %s)
                RETURNING id
                """,
                (email, email),
            )
            user = cur.fetchone()
            assert user
            cur.execute(
                """
                INSERT INTO user_password_credentials
                  (user_id, password_hash, hash_algorithm, params_json, must_rotate, disabled_at)
                VALUES (%s, %s, 'argon2id', '{}'::jsonb, false, NULL)
                """,
                (user["id"], hash_password(password)),
            )
            cur.execute(
                """
                INSERT INTO household_memberships (household_id, user_id, role)
                VALUES (%s, %s, %s)
                """,
                (uuid.UUID(household_id), user["id"], role),
            )
        conn.commit()


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 2 organization tests.",
)
def test_phase2_folder_and_tag_create_list_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, csrf = _phase2_client(monkeypatch, tmp_path, "taxonomy")
    unique = uuid.uuid4().hex[:8]

    folder_list = client.get("/api/v1/folders")
    assert folder_list.status_code == 200
    folder_names = {item["name"] for item in folder_list.json()["items"]}
    assert {"Inbox", "Needs Review"} <= folder_names

    no_csrf = client.post(
        "/api/v1/folders",
        json={"folderKind": "manual", "name": f"No CSRF {unique}"},
    )
    assert no_csrf.status_code == 403

    root = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={"folderKind": "manual", "name": f"Phase2 Root {unique}"},
    )
    assert root.status_code == 201
    root_payload = root.json()
    assert root_payload["path"] == f"/Phase2 Root {unique}"

    child = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={
            "folderKind": "manual",
            "name": f"Child {unique}",
            "parentId": root_payload["id"],
        },
    )
    assert child.status_code == 201
    assert child.json()["path"] == f"{root_payload['path']}/Child {unique}"

    duplicate = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={"folderKind": "manual", "name": f"Phase2 Root {unique}"},
    )
    assert duplicate.status_code == 409

    smart = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={
            "folderKind": "smart",
            "name": f"Needs Phase2 Review {unique}",
            "savedQuery": {"review_status": ["needs_review"]},
        },
    )
    assert smart.status_code == 201
    assert smart.json()["folderKind"] == "smart"
    assert smart.json()["savedQuery"] == {"review_status": ["needs_review"]}

    manual_saved_query = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={
            "folderKind": "manual",
            "name": f"Invalid Query {unique}",
            "savedQuery": {"tag_names": ["urgent"]},
        },
    )
    assert manual_saved_query.status_code == 422

    tag_list = client.get("/api/v1/tags")
    assert tag_list.status_code == 200
    assert "tax-relevant" in {item["name"] for item in tag_list.json()["items"]}

    no_csrf_tag = client.post("/api/v1/tags", json={"name": f"no-csrf-{unique}"})
    assert no_csrf_tag.status_code == 403

    invalid_color = client.post(
        "/api/v1/tags",
        headers={"X-CSRF-Token": csrf},
        json={"name": f"bad-color-{unique}", "colorHex": "blue"},
    )
    assert invalid_color.status_code == 422

    tag = client.post(
        "/api/v1/tags",
        headers={"X-CSRF-Token": csrf},
        json={"name": f"phase2-tag-{unique}", "colorHex": "#2563eb"},
    )
    assert tag.status_code == 201
    assert tag.json()["colorHex"] == "#2563EB"

    duplicate_tag = client.post(
        "/api/v1/tags",
        headers={"X-CSRF-Token": csrf},
        json={"name": f"PHASE2-TAG-{unique}"},
    )
    assert duplicate_tag.status_code == 409


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 2 organization tests.",
)
def test_phase2_document_organization_is_atomic_visible_and_audited(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    client, csrf = _phase2_client(monkeypatch, tmp_path, "filing")
    unique = uuid.uuid4().hex[:8]
    title = f"Phase2 Filing {unique}"
    document_id = _upload_document(client, csrf, title)

    root = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={"folderKind": "manual", "name": f"Claims {unique}"},
    ).json()
    child = client.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": csrf},
        json={"folderKind": "manual", "name": f"Medical {unique}", "parentId": root["id"]},
    ).json()
    tag_name = f"phase2-filed-{unique}"
    created_tag = client.post(
        "/api/v1/tags",
        headers={"X-CSRF-Token": csrf},
        json={"name": tag_name, "colorHex": "#0EA5E9"},
    )
    assert created_tag.status_code == 201

    without_csrf = client.post(
        f"/api/v1/documents/{document_id}/organization",
        json={"title": "Should not update"},
    )
    assert without_csrf.status_code == 403

    unknown_tag = client.post(
        f"/api/v1/documents/{document_id}/organization",
        headers={"X-CSRF-Token": csrf},
        json={"tags": [f"missing-{unique}"]},
    )
    assert unknown_tag.status_code == 422

    updated = client.post(
        f"/api/v1/documents/{document_id}/organization",
        headers={"X-CSRF-Token": csrf},
        json={
            "title": f"Filed Claim {unique}",
            "documentDate": "2026-04-24",
            "folderIds": [root["id"], child["id"]],
            "primaryFolderId": child["id"],
            "tags": [tag_name, "urgent"],
            "filingNotes": "Submitted through the Phase 2 manual filing workflow.",
        },
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["title"] == f"Filed Claim {unique}"
    assert payload["documentDate"] == "2026-04-24"
    assert payload["primaryFolderId"] == child["id"]
    assert set(payload["folderIds"]) == {root["id"], child["id"]}
    assert child["path"] in payload["folderPaths"]
    assert payload["filingNotes"] == "Submitted through the Phase 2 manual filing workflow."
    assert {tag_name, "urgent"} <= set(payload["tags"])

    by_folder = client.get("/api/v1/documents", params={"folderId": child["id"]})
    assert by_folder.status_code == 200
    assert any(item["id"] == document_id for item in by_folder.json()["items"])
    filed_summary = next(item for item in by_folder.json()["items"] if item["id"] == document_id)
    assert {tag_name, "urgent"} <= set(filed_summary["tags"])

    detail = client.get(f"/api/v1/documents/{document_id}")
    assert detail.status_code == 200
    assert detail.json()["primaryFolderId"] == child["id"]
    assert {tag_name, "urgent"} <= set(detail.json()["tags"])

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload_json
                FROM audit_events
                WHERE document_id = %s
                  AND event_name = 'document.organization_updated'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (uuid.UUID(document_id),),
            )
            audit: dict[str, Any] | None = cur.fetchone()
    assert audit is not None
    assert "folderIds" in audit["payload_json"]["changed_fields"]
    assert "tags" in audit["payload_json"]["changed_fields"]

    cleared = client.post(
        f"/api/v1/documents/{document_id}/organization",
        headers={"X-CSRF-Token": csrf},
        json={"folderIds": [], "primaryFolderId": None, "tags": [], "filingNotes": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["folderIds"] == []
    assert cleared.json()["primaryFolderId"] is None
    assert cleared.json()["tags"] == []


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 2 organization tests.",
)
def test_phase2_private_folder_is_not_visible_across_households(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    owner, owner_csrf = _phase2_client(monkeypatch, tmp_path, "owner")
    other, other_csrf = _phase2_client(monkeypatch, tmp_path, "other")
    unique = uuid.uuid4().hex[:8]

    private_folder = owner.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": owner_csrf},
        json={"folderKind": "manual", "name": f"Private {unique}", "aclMode": "private"},
    )
    assert private_folder.status_code == 201
    private_id = private_folder.json()["id"]
    other_folder_ids = {item["id"] for item in other.get("/api/v1/folders").json()["items"]}
    assert private_id not in other_folder_ids

    other_document_id = _upload_document(other, other_csrf, f"Other Filing {unique}")
    inaccessible = other.post(
        f"/api/v1/documents/{other_document_id}/organization",
        headers={"X-CSRF-Token": other_csrf},
        json={"folderIds": [private_id]},
    )
    assert inaccessible.status_code == 422


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 2 organization tests.",
)
def test_phase2_folder_names_are_unique_per_household(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    first, first_csrf = _phase2_client(monkeypatch, tmp_path, "folder-scope-a")
    second, second_csrf = _phase2_client(monkeypatch, tmp_path, "folder-scope-b")
    name = f"Shared Folder Name {uuid.uuid4().hex[:8]}"

    first_create = first.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": first_csrf},
        json={"folderKind": "manual", "name": name},
    )
    assert first_create.status_code == 201

    second_create = second.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": second_csrf},
        json={"folderKind": "manual", "name": name},
    )
    assert second_create.status_code == 201

    first_duplicate = first.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": first_csrf},
        json={"folderKind": "manual", "name": name},
    )
    assert first_duplicate.status_code == 409


@pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Set STRUCTURA_TEST_DATABASE_URL to run live Phase 2 organization tests.",
)
def test_phase2_private_folder_documents_and_assets_are_acl_protected_within_household(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    owner, owner_csrf = _phase2_client(monkeypatch, tmp_path, "private-doc-owner")
    unique = uuid.uuid4().hex[:8]
    owner_session = owner.get("/api/v1/auth/session")
    assert owner_session.status_code == 200
    household_id = owner_session.json()["householdId"]

    viewer_email = f"phase2-private-viewer-{unique}@example.com"
    viewer_password = "minimum8"
    _add_household_user(
        household_id=household_id,
        email=viewer_email,
        password=viewer_password,
        role="viewer",
    )
    viewer = TestClient(create_app())
    viewer_login = viewer.post(
        "/api/v1/auth/session",
        json={"method": "password", "email": viewer_email, "password": viewer_password},
    )
    assert viewer_login.status_code == 201

    title = f"Private Household Filing {unique}"
    document_id = _upload_document(owner, owner_csrf, title)
    private_folder = owner.post(
        "/api/v1/folders",
        headers={"X-CSRF-Token": owner_csrf},
        json={"folderKind": "manual", "name": f"Owner Private {unique}", "aclMode": "private"},
    )
    assert private_folder.status_code == 201
    private_folder_id = private_folder.json()["id"]

    filed = owner.post(
        f"/api/v1/documents/{document_id}/organization",
        headers={"X-CSRF-Token": owner_csrf},
        json={"folderIds": [private_folder_id], "primaryFolderId": private_folder_id},
    )
    assert filed.status_code == 200

    owner_detail = owner.get(f"/api/v1/documents/{document_id}")
    assert owner_detail.status_code == 200
    asset_url = owner_detail.json()["assets"][0]["assetUrl"]

    viewer_list = viewer.get("/api/v1/documents", params={"q": title})
    assert viewer_list.status_code == 200
    assert viewer_list.json()["total"] == 0
    assert viewer.get(f"/api/v1/documents/{document_id}").status_code == 404
    assert viewer.get(asset_url).status_code == 404

    owner_list = owner.get("/api/v1/documents", params={"q": title})
    assert owner_list.status_code == 200
    assert owner_list.json()["total"] == 1
