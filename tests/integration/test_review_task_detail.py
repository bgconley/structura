from __future__ import annotations

import os
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"),
    reason="Requires an isolated migrated authorization database.",
)


@pytest.fixture
def task_access(monkeypatch, tmp_path):
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "review-task-runtime"))
    get_settings.cache_clear()
    people = [
        AuthService().bootstrap_admin(
            email=f"task-reader-{uuid4()}@example.com",
            password="minimum8",
            household_name=f"Task detail {uuid4()}",
            must_rotate=False,
        )
        for _ in range(3)
    ]
    owner, member, _ = people
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO household_memberships (household_id,user_id,role) VALUES (%s,%s,'member')",
            (owner.household_id, member.user_id),
        )
        cur.execute(
            """INSERT INTO folders (name,household_id,owner_user_id,acl_mode)
               VALUES ('Private review source',%s,%s,'custom') RETURNING id""",
            (owner.household_id, owner.user_id),
        )
        folder = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO folder_acl (folder_id,principal_type,principal_id,permission)
               VALUES (%s,'user',%s,'read')""",
            (folder, member.user_id),
        )
        cur.execute(
            """INSERT INTO documents
               (title,ingestion_source,household_id,owner_user_id,primary_folder_id)
               VALUES ('Protected review source','web_upload',%s,%s,%s) RETURNING id""",
            (owner.household_id, owner.user_id, folder),
        )
        document = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO review_tasks (document_id,task_type,priority,reason)
               SELECT %s,'field_review',100,'Earlier task' FROM generate_series(1,51)""",
            (document,),
        )
        cur.execute(
            """INSERT INTO review_tasks
               (document_id,task_type,priority,reason,metadata_json)
               VALUES (%s,'field_review',1,'Protected explanation',%s) RETURNING id""",
            (document, Jsonb({"fieldPath": "invoice.total_amount", "pageNumber": 3})),
        )
        task = cur.fetchone()["id"]
    try:
        with ExitStack() as stack:
            clients = []
            for index, person in enumerate(people):
                client = stack.enter_context(TestClient(create_app()))
                login = client.post(
                    "/api/v1/auth/session",
                    json={
                        "method": "password",
                        "email": person.email,
                        "password": "minimum8",
                        "householdId": str(
                            owner.household_id if index < 2 else person.household_id
                        ),
                    },
                )
                assert login.status_code == 201, login.text
                clients.append(client)
            yield clients, folder, document, task
    finally:
        get_settings.cache_clear()


def test_exact_task_is_readable_beyond_the_first_page_and_after_resolution(task_access):
    clients, _, document, task = task_access
    owner, member, _ = clients
    backlog = owner.get("/api/v1/review-tasks", params={"status": "open"})
    assert backlog.status_code == 200
    assert len(backlog.json()["items"]) == 50
    assert str(task) not in {row["id"] for row in backlog.json()["items"]}
    path = f"/api/v1/review-tasks/{task}"
    for client in (owner, member):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.json()["id"] == str(task)
        assert response.json()["documentId"] == str(document)
        assert response.json()["fieldPath"] == "invoice.total_amount"
        assert response.json()["pageNumber"] == 3
        assert response.json()["status"] == "open"
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE review_tasks SET status='resolved' WHERE id=%s", (task,))
        cur.execute("SELECT to_jsonb(rt) AS value FROM review_tasks rt WHERE id=%s", (task,))
        before = cur.fetchone()["value"]
    assert member.get(path).json()["status"] == "resolved"
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_jsonb(rt) AS value FROM review_tasks rt WHERE id=%s", (task,))
        assert cur.fetchone()["value"] == before


def test_task_missing_cross_household_and_revoked_access_are_indistinguishable(task_access):
    clients, folder, _, task = task_access
    owner, member, outsider = clients
    path = f"/api/v1/review-tasks/{task}"
    unknown = owner.get(f"/api/v1/review-tasks/{uuid4()}")
    assert unknown.status_code == 404
    other_household = outsider.get(path)
    assert other_household.status_code == unknown.status_code
    assert other_household.json() == unknown.json() == {"detail": "Not found"}
    assert "Protected explanation" not in other_household.text
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM folder_acl WHERE folder_id=%s", (folder,))
    revoked = member.get(path)
    assert revoked.status_code == unknown.status_code
    assert revoked.json() == unknown.json()
    assert owner.get(path).status_code == 200
    assert member.get("/api/v1/review-tasks").json()["items"] == []
