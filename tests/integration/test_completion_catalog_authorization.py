from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.sql import SQL

from apps.api.structura_api.main import create_app
from lib.auth import AuthService
from lib.auth.service import BootstrapResult
from lib.config import get_settings
from lib.db.connection import db_connection

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"), reason="Isolated test database required"
)


def sql(statement, params=()):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(statement, params)
            rows = cur.fetchall() if cur.description else []
        conn.commit()
    return rows


def post(client, path, payload):
    return client.post(
        path, json=payload, headers={"X-CSRF-Token": client.cookies["structura_csrf"]}
    )


def login(principal, household_id=None):
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/auth/session",
        json={
            "method": "password",
            "email": principal.email,
            "password": "minimum8",
            "householdId": str(household_id or principal.household_id),
        },
    )
    assert response.status_code == 201, response.text
    return client


@dataclass
class Household:
    principal: BootstrapResult
    client: TestClient
    document: UUID


@pytest.fixture
def households(monkeypatch, tmp_path):
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    get_settings.cache_clear()
    result = []
    for _ in range(2):
        unique = uuid4().hex
        principal = AuthService().bootstrap_admin(
            email=f"catalog-{unique}@example.com",
            password="minimum8",
            household_name=f"Catalog {unique}",
        )
        document = sql(
            """INSERT INTO documents (title,ingestion_source,household_id,owner_user_id)
            VALUES ('Catalog document','web_upload',%s,%s) RETURNING id""",
            (principal.household_id, principal.user_id),
        )[0]["id"]
        result.append(Household(principal, login(principal), document))
    yield result
    get_settings.cache_clear()


def test_custom_tags_are_household_scoped_for_discovery_creation_and_filing(households):
    first, second = households
    shared_name = f"same-name-{uuid4().hex}"
    first_tag = post(first.client, "/api/v1/tags", {"name": shared_name})
    assert first_tag.status_code == 201, first_tag.text
    assert first_tag.json()["id"] not in {
        row["id"] for row in second.client.get("/api/v1/tags").json()["items"]
    }
    foreign_filing = post(
        second.client,
        f"/api/v1/documents/{second.document}/organization",
        {"tags": [shared_name]},
    )
    assert foreign_filing.status_code == 422, foreign_filing.text
    assert sql("SELECT * FROM document_tags WHERE document_id=%s", (second.document,)) == []

    second_tag = post(second.client, "/api/v1/tags", {"name": shared_name.upper()})
    assert second_tag.status_code == 201, second_tag.text
    assert first_tag.json()["id"] != second_tag.json()["id"]
    assert post(first.client, "/api/v1/tags", {"name": shared_name.upper()}).status_code == 409
    for household, tag in ((first, first_tag), (second, second_tag)):
        own_filing = post(
            household.client,
            f"/api/v1/documents/{household.document}/organization",
            {"tags": [shared_name]},
        )
        assert own_filing.status_code == 200, own_filing.text
        links = sql("SELECT tag_id FROM document_tags WHERE document_id=%s", (household.document,))
        assert links == [{"tag_id": UUID(tag.json()["id"])}]


def test_seeded_system_tags_remain_shared_read_only_and_assignable(households):
    system = sql("SELECT * FROM tags WHERE is_system ORDER BY name LIMIT 1")[0]
    for household in households:
        visible = household.client.get("/api/v1/tags").json()["items"]
        assert any(row["id"] == str(system["id"]) for row in visible)
        assert (
            post(
                household.client, "/api/v1/tags", {"name": str(system["name"]).upper()}
            ).status_code
            == 409
        )
        assigned = post(
            household.client,
            f"/api/v1/documents/{household.document}/organization",
            {"tags": [str(system["name"])]},
        )
        assert assigned.status_code == 200, assigned.text
    assert sql("SELECT * FROM tags WHERE id=%s", (system["id"],)) == [system]


def test_legacy_tag_upgrade_preserves_links_and_ownership_without_guessing(households):
    first, second = households
    migration = (
        Path(__file__).resolve().parents[2] / "database/093_completion_household_tags.sql"
    ).read_text()
    # Stage the old unscoped representation, then execute the actual upgrade SQL.
    # Roll it all back so a migration regression cannot pollute later fixtures.
    with db_connection() as conn:
        with conn.cursor() as cur:
            tags = {}
            for kind in ("single", "shared", "unused"):
                cur.execute(
                    """INSERT INTO tags (name,color_hex,description)
                    VALUES (%s,'#abcdef','Legacy description') RETURNING *""",
                    (f"legacy-{kind}-{uuid4().hex}",),
                )
                row = cur.fetchone()
                assert row is not None
                tags[kind] = row
            for doc, tag in (
                (first.document, tags["single"]),
                (first.document, tags["shared"]),
                (second.document, tags["shared"]),
            ):
                cur.execute(
                    "INSERT INTO document_tags (document_id,tag_id) VALUES (%s,%s)",
                    (doc, tag["id"]),
                )
            cur.execute("UPDATE documents SET deleted_at=now() WHERE id=%s", (second.document,))
            cur.execute(SQL(cast(LiteralString, migration)), prepare=False)
            cur.execute("SELECT * FROM tags WHERE id=%s", (tags["single"]["id"],))
            single = cur.fetchone()
            assert single is not None
            assert single["household_id"] == first.principal.household_id
            assert single["created_at"] == tags["single"]["created_at"]
            cur.execute(
                """SELECT m.household_id,m.scoped_tag_id,t.name,t.color_hex,t.description,
                          t.created_at,dt.document_id
                FROM tag_household_migrations m JOIN tags t ON t.id=m.scoped_tag_id
                JOIN document_tags dt ON dt.tag_id=t.id WHERE m.legacy_tag_id=%s""",
                (tags["shared"]["id"],),
            )
            mapped = cur.fetchall()
            assert len(mapped) == 2
            assert {(row["household_id"], row["document_id"]) for row in mapped} == {
                (first.principal.household_id, first.document),
                (second.principal.household_id, second.document),
            }
            assert len({row["scoped_tag_id"] for row in mapped}) == 2
            for row in mapped:
                assert row["scoped_tag_id"] != tags["shared"]["id"]
                for field in ("name", "color_hex", "description", "created_at"):
                    assert row[field] == tags["shared"][field]
            for kind in ("shared", "unused"):
                cur.execute("SELECT household_id FROM tags WHERE id=%s", (tags[kind]["id"],))
                legacy = cur.fetchone()
                assert legacy is not None and legacy["household_id"] is None
            cur.execute(
                "SELECT * FROM tag_household_migrations WHERE legacy_tag_id=%s",
                (tags["unused"]["id"],),
            )
            assert cur.fetchall() == []
            for household in households:
                cur.execute(
                    "SELECT id FROM tags WHERE household_id=%s OR is_system",
                    (household.principal.household_id,),
                )
                visible = {row["id"] for row in cur.fetchall()}
                assert tags["unused"]["id"] not in visible
                assert tags["shared"]["id"] not in visible
        conn.rollback()


def test_contact_counts_follow_document_acl_without_alias_or_role_fanout(households):
    owner, member = households
    sql(
        "INSERT INTO household_memberships (household_id,user_id,role) VALUES (%s,%s,'member')",
        (owner.principal.household_id, member.principal.user_id),
    )
    client = login(member.principal, owner.principal.household_id)
    created = post(
        owner.client,
        "/api/v1/contacts",
        {"displayName": f"Count contact {uuid4().hex}", "aliases": ["Alias one", "Alias two"]},
    )
    assert created.status_code == 201, created.text
    contact_id = UUID(created.json()["id"])
    for role in ("issuer", "recipient"):
        sql(
            "INSERT INTO document_contacts (document_id,contact_id,role_name) VALUES (%s,%s,%s)",
            (owner.document, contact_id, role),
        )
    folder = sql(
        """INSERT INTO folders (name,household_id,owner_user_id,acl_mode,folder_kind)
        VALUES (%s,%s,%s,'custom','manual') RETURNING id""",
        (uuid4().hex, owner.principal.household_id, owner.principal.user_id),
    )[0]["id"]
    sql("UPDATE documents SET primary_folder_id=%s WHERE id=%s", (folder, owner.document))

    def contact_for(actor):
        response = actor.get("/api/v1/contacts")
        assert response.status_code == 200, response.text
        return next(row for row in response.json()["items"] if row["id"] == str(contact_id))

    assert contact_for(client)["linkedDocumentCount"] == 0
    assert contact_for(owner.client)["linkedDocumentCount"] == 1
    assert contact_for(client)["aliases"] == ["Alias one", "Alias two"]
    sql(
        "INSERT INTO folder_acl (folder_id,principal_type,principal_id,permission) "
        "VALUES (%s,'user',%s,'read')",
        (folder, member.principal.user_id),
    )
    assert contact_for(client)["linkedDocumentCount"] == 1
    sql("UPDATE documents SET deleted_at=now() WHERE id=%s", (owner.document,))
    assert contact_for(client)["linkedDocumentCount"] == 0
    sql("UPDATE documents SET deleted_at=NULL WHERE id=%s", (owner.document,))
    sql("DELETE FROM folder_acl WHERE folder_id=%s", (folder,))
    assert contact_for(client)["linkedDocumentCount"] == 0
