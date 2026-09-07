from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.structura_api.main import create_app
from lib.auth import AuthService, hash_secret
from lib.automation import service as automation_service
from lib.config import get_settings
from lib.contacts import repository as contact_repository
from lib.db.connection import db_connection
from lib.jobs import JobService
from lib.relationships import relationship_repository
from lib.relationships import service as relationship_service
from lib.storage import ObjectStorage

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"), reason="Isolated test database required"
)


def sql(statement, params=()):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params)
            result = cur.fetchall() if cur.description else []
        conn.commit()
    return result


@dataclass
class Archive:
    household: UUID
    owner: UUID
    member: UUID
    folder: UUID
    document: UUID
    owner_client: TestClient
    member_client: TestClient


def login(email: str, household: UUID) -> TestClient:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/auth/session",
        json={
            "method": "password",
            "email": email,
            "password": "minimum8",
            "householdId": str(household),
        },
    )
    assert response.status_code == 201, response.text
    return client


@pytest.fixture
def archive(monkeypatch, tmp_path):
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    get_settings.cache_clear()
    unique = uuid4().hex
    owner = AuthService().bootstrap_admin(
        email=f"owner-{unique}@example.com", password="minimum8", household_name=f"Owner {unique}"
    )
    member = AuthService().bootstrap_admin(
        email=f"member-{unique}@example.com", password="minimum8", household_name=f"Other {unique}"
    )
    sql(
        "INSERT INTO household_memberships (household_id, user_id, role) VALUES (%s,%s,'member')",
        (owner.household_id, member.user_id),
    )
    folder = sql(
        """INSERT INTO folders (name, household_id, owner_user_id, acl_mode, folder_kind)
        VALUES (%s,%s,%s,'custom','manual') RETURNING id""",
        (f"Private {unique}", owner.household_id, owner.user_id),
    )[0]["id"]
    document = sql(
        """INSERT INTO documents
        (title, ingestion_source, household_id, owner_user_id, primary_folder_id)
        VALUES (%s,'web_upload',%s,%s,%s) RETURNING id""",
        (f"Authorization {unique}", owner.household_id, owner.user_id, folder),
    )[0]["id"]
    sql(
        "INSERT INTO folder_acl (folder_id,principal_type,principal_id,permission) "
        "VALUES (%s,'user',%s,'read')",
        (folder, member.user_id),
    )
    yield Archive(
        owner.household_id,
        owner.user_id,
        member.user_id,
        folder,
        document,
        login(owner.email, owner.household_id),
        login(member.email, owner.household_id),
    )
    get_settings.cache_clear()


def token_client(archive, scopes, user_id=None):
    token = uuid4().hex
    sql(
        """INSERT INTO api_tokens (user_id,household_id,label,token_hash,scopes)
        VALUES (%s,%s,'SEC01 test',%s,%s)""",
        (user_id or archive.owner, archive.household, hash_secret(token), scopes),
    )
    return TestClient(create_app(), headers={"X-API-Token": token}), token


def post(client, path, payload):
    csrf = client.cookies.get("structura_csrf")
    return client.post(path, json=payload, headers={"X-CSRF-Token": csrf} if csrf else {})


def permissions(archive, role="owner"):
    return sql(
        """SELECT document_is_readable(%s,%s,%s,%s) AS readable,
        document_is_writable(%s,%s,%s,%s) AS writable""",
        (
            archive.document,
            archive.household,
            archive.member,
            role,
            archive.document,
            archive.household,
            archive.member,
            role,
        ),
    )[0]


@pytest.mark.parametrize("folder_mode", ["private", "custom"])
@pytest.mark.parametrize("grant,can_write", [("read", False), ("write", True), ("admin", True)])
def test_folder_grants_are_not_document_write_grants_unless_writable(
    archive, folder_mode, grant, can_write
):
    sql("UPDATE folders SET acl_mode=%s WHERE id=%s", (folder_mode, archive.folder))
    sql("UPDATE folder_acl SET permission=%s WHERE folder_id=%s", (grant, archive.folder))
    # Supplied owner role is deliberately spoofed: actual membership is member.
    assert permissions(archive) == {"readable": True, "writable": can_write}
    for mode in ("private", "custom"):
        sql("UPDATE documents SET acl_mode=%s WHERE id=%s", (mode, archive.document))
        assert permissions(archive) == {"readable": False, "writable": False}


def test_membership_role_sensitivity_and_household_are_authoritative(archive):
    sql("UPDATE folders SET acl_mode='household' WHERE id=%s", (archive.folder,))
    assert permissions(archive) == {"readable": True, "writable": True}
    sql("UPDATE documents SET sensitivity='highly_sensitive' WHERE id=%s", (archive.document,))
    assert permissions(archive) == {"readable": False, "writable": False}
    sql("UPDATE documents SET owner_user_id=%s WHERE id=%s", (archive.member, archive.document))
    assert permissions(archive) == {"readable": True, "writable": True}
    sql(
        "UPDATE household_memberships SET role='viewer' WHERE household_id=%s AND user_id=%s",
        (archive.household, archive.member),
    )
    assert permissions(archive) == {"readable": True, "writable": False}
    sql(
        "UPDATE documents SET household_id=%s WHERE id=%s",
        (
            sql(
                "SELECT household_id FROM household_memberships WHERE user_id=%s AND role='owner'",
                (archive.member,),
            )[0]["household_id"],
            archive.document,
        ),
    )
    assert permissions(archive) == {"readable": False, "writable": False}


def test_read_grant_cannot_mutate_and_write_grant_preserves_editing(archive):
    client, doc = archive.member_client, str(archive.document)
    assert client.get(f"/api/v1/documents/{doc}").status_code == 200
    before = sql(
        "SELECT title, review_status, updated_at FROM documents WHERE id=%s", (archive.document,)
    )
    assert (
        post(client, f"/api/v1/documents/{doc}/organization", {"title": "Unauthorized"}).status_code
        == 404
    )
    correction = {
        "documentId": doc,
        "actionType": "correct_field",
        "fieldPath": "invoice.total",
        "newValue": 0,
        "metadata": {"valueType": "number"},
    }
    assert post(client, f"/api/v1/documents/{doc}/review-actions", correction).status_code in (
        400,
        404,
    )
    assert post(
        client,
        f"/api/v1/documents/{doc}/review-actions",
        {"documentId": doc, "actionType": "rerun_extraction"},
    ).status_code in (400, 404)
    assert (
        post(
            client,
            "/api/v1/relationships",
            {"fromDocumentId": doc, "toDocumentId": str(uuid4()), "relationshipType": "related_to"},
        ).status_code
        == 404
    )
    assert before == sql(
        "SELECT title, review_status, updated_at FROM documents WHERE id=%s", (archive.document,)
    )
    for table in ("canonical_fields", "review_events", "pipeline_jobs"):
        assert (
            sql(f"SELECT count(*) AS count FROM {table} WHERE document_id=%s", (archive.document,))[
                0
            ]["count"]
            == 0
        )
    assert (
        sql("SELECT count(*) AS count FROM audit_events WHERE entity_id=%s", (archive.document,))[
            0
        ]["count"]
        == 0
    )
    sql("UPDATE folder_acl SET permission='write' WHERE folder_id=%s", (archive.folder,))
    assert (
        post(client, f"/api/v1/documents/{doc}/organization", {"title": "Authorized"}).status_code
        == 200
    )
    # Source permission alone cannot authorize a different private target folder.
    target = sql(
        """INSERT INTO folders (name, household_id, owner_user_id, acl_mode)
        VALUES (%s,%s,%s,'private') RETURNING id""",
        (uuid4().hex, archive.household, archive.owner),
    )[0]["id"]
    assert (
        post(
            client,
            f"/api/v1/documents/{doc}/organization",
            {"primaryFolderId": str(target), "folderIds": [str(target)]},
        ).status_code
        == 422
    )
    assert (
        sql("SELECT primary_folder_id FROM documents WHERE id=%s", (archive.document,))[0][
            "primary_folder_id"
        ]
        == archive.folder
    )


def test_owner_read_token_and_member_admin_token_cannot_write_or_admin(archive):
    client, _ = token_client(archive, ["documents:read"])
    assert client.get(f"/api/v1/documents/{archive.document}").status_code == 200
    assert (
        post(
            client, f"/api/v1/documents/{archive.document}/organization", {"title": "No"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/admin/jobs").status_code == 403
    assert client.get("/api/v1/admin/service-health").status_code == 403
    assert post(client, f"/api/v1/admin/jobs/{uuid4()}/cancel", {"reason": "No"}).status_code == 403
    member, _ = token_client(archive, ["admin"], archive.member)
    assert member.get("/api/v1/admin/jobs").status_code == 403
    assert member.get("/api/v1/admin/service-health").status_code == 403
    service_only, _ = token_client(archive, ["service:admin"])
    assert service_only.get(f"/api/v1/documents/{archive.document}/parse-debug").status_code == 403


def test_membership_removal_invalidates_session_token_and_introspection(archive):
    token, raw_token = token_client(archive, ["documents:read"], archive.member)
    session_token = archive.member_client.cookies["structura_session"]
    assert AuthService().resolve_api_token(raw_token)
    assert AuthService().resolve_session_token(session_token)
    sql(
        "DELETE FROM household_memberships WHERE household_id=%s AND user_id=%s",
        (archive.household, archive.member),
    )
    assert AuthService().resolve_api_token(raw_token) is None
    assert AuthService().resolve_session_token(session_token) is None
    assert AuthService().get_session_info(session_token) is None
    assert token.get("/api/v1/documents").status_code == 401
    assert archive.member_client.get("/api/v1/auth/session").status_code == 401
    assert permissions(archive) == {"readable": False, "writable": False}


def test_job_read_tracks_document_acl_and_hides_private_ids(archive):
    job = JobService().create_job(
        job_type="ingest",
        household_id=archive.household,
        document_id=archive.document,
        payload={"document_id": str(archive.document)},
    )
    path = f"/api/v1/jobs/{job.job_id}"
    assert archive.member_client.get(path).status_code == 200
    sql("DELETE FROM folder_acl WHERE folder_id=%s", (archive.folder,))
    denied = archive.member_client.get(path)
    missing = archive.member_client.get(f"/api/v1/jobs/{uuid4()}")
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()
    assert archive.owner_client.get(path).status_code == 200
    assert archive.member_client.get("/api/v1/admin/jobs").status_code == 403


def test_primary_folder_revocation_applies_to_assets_search_facets_and_review(archive):
    doc = str(archive.document)
    query = "authorizationneedle"
    stored = ObjectStorage().store_bytes(
        b"isolated protected evidence", kind="canonical", role="original"
    )
    asset = sql(
        """INSERT INTO document_assets (document_id, asset_role, uri, sha256, byte_size)
        VALUES (%s,'original',%s,%s,%s) RETURNING id""",
        (archive.document, stored.uri, stored.sha256, stored.byte_size),
    )[0]["id"]
    sql(
        "INSERT INTO document_chunks (document_id, chunk_index, text_content) VALUES (%s,1,%s)",
        (archive.document, query),
    )
    sql("SELECT refresh_document_chunk_projection(%s)", (archive.document,))
    sql(
        "INSERT INTO review_tasks (document_id,task_type,reason) "
        "VALUES (%s,'document_quality','Test')",
        (archive.document,),
    )
    client = archive.member_client
    assert client.get(f"/api/v1/assets/{asset}").content == b"isolated protected evidence"
    assert any(item["id"] == doc for item in client.get("/api/v1/documents").json()["items"])
    search = client.post("/api/v1/search", json={"query": query, "mode": "lexical"})
    assert search.status_code == 200, search.text
    assert any(item["documentId"] == doc for item in search.json()["items"])
    assert client.get(f"/api/v1/documents/{doc}/field-candidates").status_code == 200
    assert any(
        item["documentId"] == doc for item in client.get("/api/v1/review-tasks").json()["items"]
    )
    sql("DELETE FROM folder_acl WHERE folder_id=%s", (archive.folder,))
    # Underspecified role grants must never become an accidental allow rule.
    sql(
        """INSERT INTO folder_acl (folder_id,principal_type,principal_id,permission)
        VALUES (%s,'role',%s,'admin')""",
        (archive.folder, archive.member),
    )
    assert client.get(f"/api/v1/assets/{asset}").status_code == 404
    assert client.get(f"/api/v1/documents/{doc}").status_code == 404
    assert client.get(f"/api/v1/documents/{doc}/field-candidates").status_code == 404
    hidden_documents = client.get("/api/v1/documents").json()
    assert hidden_documents["items"] == []
    assert hidden_documents["total"] == hidden_documents["corpusTotal"] == 0
    assert all(count == 0 for count in hidden_documents["counts"].values())
    hidden_search = client.post("/api/v1/search", json={"query": query, "mode": "lexical"})
    assert hidden_search.status_code == 200
    assert hidden_search.json()["items"] == []
    assert not any(hidden_search.json()["facets"][key] for key in ("families", "folders", "tags"))
    assert client.get("/api/v1/review-tasks").json()["items"] == []


def test_live_role_downgrade_and_disabled_user_restrict_existing_credentials(archive):
    client, raw_token = token_client(archive, ["documents:write"], archive.member)
    sql("UPDATE folder_acl SET permission='write' WHERE folder_id=%s", (archive.folder,))
    assert (
        post(
            client, f"/api/v1/documents/{archive.document}/organization", {"title": "Allowed"}
        ).status_code
        == 200
    )
    sql(
        "UPDATE household_memberships SET role='viewer' WHERE household_id=%s AND user_id=%s",
        (archive.household, archive.member),
    )
    assert AuthService().resolve_api_token(raw_token).household_role == "viewer"
    assert (
        post(
            client, f"/api/v1/documents/{archive.document}/organization", {"title": "Denied"}
        ).status_code
        == 403
    )
    assert post(archive.member_client, "/api/v1/tags", {"name": uuid4().hex}).status_code == 403
    sql("UPDATE users SET is_disabled=true WHERE id=%s", (archive.member,))
    assert client.get("/api/v1/documents").status_code == 401
    assert archive.member_client.get("/api/v1/documents").status_code == 401
    assert permissions(archive) == {"readable": False, "writable": False}


def related_document(archive):
    return sql(
        """INSERT INTO documents
        (title,ingestion_source,household_id,owner_user_id,primary_folder_id)
        VALUES ('Related','web_upload',%s,%s,%s) RETURNING id""",
        (archive.household, archive.owner, archive.folder),
    )[0]["id"]


def suggested_relationship(archive, other):
    return sql(
        """INSERT INTO document_relationships
        (from_document_id,to_document_id,relationship_type,status,source_engine)
        VALUES (%s,%s,'related_to','suggested','system') RETURNING id""",
        (archive.document, other),
    )[0]["id"]


def observe_lock_backend(monkeypatch, module, attribute):
    """Observe the real request connection without replacing its lock/SQL behavior."""
    original = getattr(module, attribute)
    backends = Queue()

    def observed(cur, *args, **kwargs):
        backends.put(cur.connection.info.backend_pid)
        return original(cur, *args, **kwargs)

    monkeypatch.setattr(module, attribute, observed)
    return backends


def wait_until_blocked(cur, blocker_pid, waiting_pid):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        cur.execute("SELECT %s = ANY(pg_blocking_pids(%s)) AS blocked", (blocker_pid, waiting_pid))
        if cur.fetchone()["blocked"]:
            return
        time.sleep(0.01)
    pytest.fail("Mutation did not wait for the competing transaction's row lock")


@pytest.mark.parametrize("action", ["create", "accept", "reject"])
def test_relationship_rechecks_access_after_blocked_refile(archive, monkeypatch, action):
    sql("UPDATE folder_acl SET permission='write' WHERE folder_id=%s", (archive.folder,))
    other = related_document(archive)
    relationship = suggested_relationship(archive, other) if action != "create" else None
    module = relationship_service if action == "create" else relationship_repository
    backends = observe_lock_backend(monkeypatch, module, "lock_writable_documents")
    path = (
        "/api/v1/relationships"
        if action == "create"
        else f"/api/v1/relationships/{relationship}/{action}"
    )
    payload = (
        {
            "fromDocumentId": str(archive.document),
            "toDocumentId": str(other),
            "relationshipType": "related_to",
        }
        if action == "create"
        else {}
    )
    with db_connection() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        with blocker.cursor() as cur:
            cur.execute("UPDATE documents SET acl_mode='private' WHERE id=%s", (other,))
            request = pool.submit(post, archive.member_client, path, payload)
            try:
                wait_until_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            response = request.result(timeout=10)
    assert response.status_code == 404, response.text
    rows = sql(
        "SELECT status FROM document_relationships WHERE from_document_id=%s", (archive.document,)
    )
    assert rows == ([{"status": "suggested"}] if relationship else [])
    assert (
        sql("SELECT count(*) AS n FROM review_events WHERE document_id=%s", (archive.document,))[0][
            "n"
        ]
        == 0
    )
    assert (
        sql("SELECT count(*) AS n FROM audit_events WHERE entity_id=%s", (relationship,))[0]["n"]
        == 0
    )


@pytest.mark.parametrize("action", ["reject", "defer"])
def test_filing_suggestion_rechecks_access_after_blocked_refile(archive, monkeypatch, action):
    sql("UPDATE folder_acl SET permission='write' WHERE folder_id=%s", (archive.folder,))
    rule = sql(
        "INSERT INTO filing_rules (household_id,name) VALUES (%s,%s) RETURNING id",
        (archive.household, uuid4().hex),
    )[0]["id"]
    run = sql(
        """INSERT INTO filing_rule_runs (rule_id,document_id,mode,decision_status)
        VALUES (%s,%s,'suggest','pending') RETURNING id""",
        (rule, archive.document),
    )[0]["id"]
    # Observe the current outer filing lock without replacing SQL or authorization.
    backends = observe_lock_backend(monkeypatch, automation_service, "lock_writable_document")
    with db_connection() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        with blocker.cursor() as cur:
            cur.execute("UPDATE documents SET acl_mode='private' WHERE id=%s", (archive.document,))
            request = pool.submit(
                post, archive.member_client, f"/api/v1/filing-suggestions/{run}/{action}", {}
            )
            try:
                wait_until_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            response = request.result(timeout=10)
    assert response.status_code == 404, response.text
    assert (
        sql("SELECT decision_status FROM filing_rule_runs WHERE id=%s", (run,))[0][
            "decision_status"
        ]
        == "pending"
    )


def test_contact_merge_waits_for_concurrent_link_and_keeps_private_link(archive, monkeypatch):
    contacts = [
        sql(
            """INSERT INTO contacts (household_id,contact_type,display_name)
        VALUES (%s,'merchant',%s) RETURNING id""",
            (archive.household, uuid4().hex),
        )[0]["id"]
        for _ in range(2)
    ]
    source, target = contacts
    sql("UPDATE documents SET acl_mode='private' WHERE id=%s", (archive.document,))
    backends = observe_lock_backend(monkeypatch, contact_repository, "lock_contacts")
    with db_connection() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        with blocker.cursor() as cur:
            # Same contacts-before-documents protocol as the document-link service.
            cur.execute("SELECT id FROM contacts WHERE id=%s FOR UPDATE", (source,))
            cur.execute(
                """INSERT INTO document_contacts (document_id,contact_id,role_name)
                VALUES (%s,%s,'issuer')""",
                (archive.document, source),
            )
            request = pool.submit(
                post,
                archive.member_client,
                f"/api/v1/contacts/{source}/merge",
                {"targetContactId": str(target)},
            )
            try:
                wait_until_blocked(cur, blocker.info.backend_pid, backends.get(timeout=5))
            finally:
                blocker.commit()
            response = request.result(timeout=10)
    assert response.status_code == 404, response.text
    assert len(sql("SELECT id FROM contacts WHERE id=ANY(%s::uuid[])", (contacts,))) == 2
    assert sql(
        "SELECT contact_id FROM document_contacts WHERE document_id=%s", (archive.document,)
    ) == [{"contact_id": source}]
    assert (
        sql(
            "SELECT count(*) AS n FROM audit_events "
            "WHERE entity_id=%s AND event_name='contact.merged'",
            (target,),
        )[0]["n"]
        == 0
    )


def test_review_only_token_can_decide_relationships_but_cannot_create_them(archive):
    sql("UPDATE folder_acl SET permission='write' WHERE folder_id=%s", (archive.folder,))
    other = related_document(archive)
    relationship = suggested_relationship(archive, other)
    client, _ = token_client(archive, ["documents:review"], archive.member)
    review_path = f"/api/v1/documents/{archive.document}/review-actions"
    accepted = post(
        client,
        review_path,
        {
            "documentId": str(archive.document),
            "actionType": "accept_relationship",
            "metadata": {"relationshipId": str(relationship)},
        },
    )
    assert accepted.status_code == 200, accepted.text
    rejected = post(client, f"/api/v1/relationships/{relationship}/reject", {})
    assert rejected.status_code == 200, rejected.text
    assert (
        post(
            client,
            "/api/v1/relationships",
            {
                "fromDocumentId": str(archive.document),
                "toDocumentId": str(other),
                "relationshipType": "related_to",
            },
        ).status_code
        == 403
    )
    sql("UPDATE folder_acl SET permission='read' WHERE folder_id=%s", (archive.folder,))
    assert post(client, f"/api/v1/relationships/{relationship}/accept", {}).status_code == 404
    assert (
        sql("SELECT status FROM document_relationships WHERE id=%s", (relationship,))[0]["status"]
        == "rejected"
    )
