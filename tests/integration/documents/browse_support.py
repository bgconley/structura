from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from typing import LiteralString
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.structura_api.main import create_app
from lib.auth import AuthService, BootstrapResult
from lib.db.connection import db_connection


def browse_rows(statement: LiteralString, params=()):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall() if cur.description else []


def create_identity(label: str) -> BootstrapResult:
    return AuthService().bootstrap_admin(
        email=f"browse-{label}-{uuid4().hex}@example.com",
        password="minimum8",
        household_name=f"Browse {label} {uuid4().hex}",
        must_rotate=False,
    )


def login(identity: BootstrapResult, household_id: UUID | None = None) -> TestClient:
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/auth/session",
        json={
            "method": "password",
            "email": identity.email,
            "password": "minimum8",
            "householdId": str(household_id or identity.household_id),
        },
    )
    assert response.status_code == 201, response.text
    return client


@dataclass
class BrowseCorpus:
    identity: BootstrapResult
    client: TestClient

    def document(self, title: str, *, owner: BootstrapResult | None = None) -> UUID:
        identity = owner or self.identity
        return browse_rows(
            """INSERT INTO documents (title, household_id, owner_user_id, ingestion_source)
            VALUES (%s,%s,%s,'web_upload') RETURNING id""",
            (title, identity.household_id, identity.user_id),
        )[0]["id"]

    def list(self, **params):
        response = self.client.get("/api/v1/documents", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    def folder(self, *, kind="manual", acl_mode="household") -> UUID:
        return browse_rows(
            """INSERT INTO folders
            (name, household_id, owner_user_id, folder_kind, acl_mode)
            VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            (
                f"Browse folder {uuid4().hex}",
                self.identity.household_id,
                self.identity.user_id,
                kind,
                acl_mode,
            ),
        )[0]["id"]

    def model_classification(self, document_id: UUID, *, confidence=0.4) -> None:
        browse_rows(
            "UPDATE documents SET family_confidence=%s WHERE id=%s",
            (confidence, document_id),
        )
        browse_rows(
            """INSERT INTO document_extractions
            (document_id,schema_name,schema_version,status,source_engine,confidence)
            VALUES (%s,'document_classification','v1','completed','system',%s)""",
            (document_id, confidence),
        )


def seed_paged_documents(corpus: BrowseCorpus, count=207):
    documents = []
    for index in range(count):
        documents.append(
            {
                "id": uuid4(),
                "title": f"Browse {index % 9:02d}",
                "created": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=index // 7),
                "date": None if index % 4 == 0 else date(2025, 1, index % 28 + 1),
                "hash": sha256(f"browse-{index}".encode()).hexdigest(),
            }
        )
    with db_connection() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO documents
            (id,title,created_at,document_date,original_sha256,
             household_id,owner_user_id,ingestion_source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'web_upload')""",
            [
                (
                    row["id"],
                    row["title"],
                    row["created"],
                    row["date"],
                    row["hash"],
                    corpus.identity.household_id,
                    corpus.identity.user_id,
                )
                for row in documents
            ],
        )
    return documents
