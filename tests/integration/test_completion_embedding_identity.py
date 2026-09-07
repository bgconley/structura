from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.model_runtime.clients.visual_embeddings import VisualEmbeddingClient
from lib.model_runtime.profiles import VISUAL_EMBED_BLACKBIRD_PROFILE, get_model_profile
from lib.search.embedding_gateway import (
    DeterministicVisualEmbeddingGateway,
    VisualEmbeddingInput,
    default_visual_embedding_profile,
)
from lib.search.embedding_repository import list_visual_embedding_sources, persist_embedding
from lib.search.embeddings.visual_model import VisualModelEmbeddingGateway

pytestmark = pytest.mark.skipif(
    not os.environ.get("STRUCTURA_TEST_DATABASE_URL"), reason="Isolated test database required"
)


@pytest.fixture
def source_document(monkeypatch):
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", os.environ["STRUCTURA_TEST_DATABASE_URL"])
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    owner = AuthService().bootstrap_admin(
        email=f"embedding-{uuid4()}@example.com",
        password="minimum8",
        household_name=f"Embedding {uuid4()}",
    )
    image = b"controlled image bytes for adapter persistence tests"
    digest = hashlib.sha256(image).hexdigest()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO documents (title, ingestion_source, household_id, owner_user_id)
            VALUES ('Original descriptor', 'web_upload', %s, %s) RETURNING id""",
            (owner.household_id, owner.user_id),
        )
        document = cur.fetchone()
        assert document is not None
        document_id = document["id"]
        cur.execute(
            """INSERT INTO document_assets
            (document_id, asset_role, uri, mime_type, byte_size, sha256)
            VALUES (%s, 'page_image', %s, 'image/png', %s, %s) RETURNING id""",
            (document_id, f"object://embedding-test/{uuid4()}", len(image), digest),
        )
        asset = cur.fetchone()
        assert asset is not None
        asset_id = asset["id"]
        cur.execute(
            """INSERT INTO document_pages
            (document_id, page_number, image_asset_id, metadata_json)
            VALUES (%s, 1, %s, '{"phase8":{"quality":{"visualEmbeddingEligible":true}}}')""",
            (document_id, asset_id),
        )
    yield document_id, image
    get_settings.cache_clear()


def embed_source(cur, document_id, image, gateway):
    source = list_visual_embedding_sources(cur, document_id)[0]
    result = gateway.embed_assets(
        [
            VisualEmbeddingInput(
                descriptor_text=source.text,
                image_bytes=image,
                mime_type=str(source.metadata["assetMimeType"]),
                content_sha256=source.content_sha256,
            )
        ]
    )[0]
    return source, result


def rows(cur, document_id):
    cur.execute(
        "SELECT is_active, metadata_json FROM embeddings "
        "WHERE document_id=%s ORDER BY created_at, id",
        (document_id,),
    )
    return cur.fetchall()


@pytest.mark.parametrize("live_adapter", [False, True], ids=["fixture", "model-http-mock"])
def test_same_image_with_changed_descriptor_gets_a_new_embedding(source_document, live_adapter):
    document_id, image = source_document
    if live_adapter:
        model_profile = get_model_profile(VISUAL_EMBED_BLACKBIRD_PROFILE)
        client = VisualEmbeddingClient(
            profile=model_profile,
            http_client_base_url="http://embedding.test",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "model": model_profile.base_model,
                        "data": [{"index": 0, "embedding": [1.0, *([0.0] * 2047)]}],
                    },
                )
            ),
        )
        gateway = VisualModelEmbeddingGateway(client=client, profile_name=model_profile.name)
    else:
        gateway = DeterministicVisualEmbeddingGateway(default_visual_embedding_profile(2048))
    with db_connection() as conn, conn.cursor() as cur:
        source, first = embed_source(cur, document_id, image, gateway)
        assert persist_embedding(cur, source=source, embedding=first, force_reembed=False)
        assert not persist_embedding(cur, source=source, embedding=first, force_reembed=False)
        cur.execute("UPDATE documents SET title='Changed descriptor' WHERE id=%s", (document_id,))
        changed_source, changed = embed_source(cur, document_id, image, gateway)
        assert source.content_sha256 == changed_source.content_sha256
        assert source.text != changed_source.text
        assert first.input_identity != changed.input_identity
        assert persist_embedding(cur, source=changed_source, embedding=changed, force_reembed=False)
        assert not persist_embedding(
            cur, source=changed_source, embedding=changed, force_reembed=False
        )
        persisted = rows(cur, document_id)
        assert len(persisted) == 2
        assert sum(row["is_active"] for row in persisted) == 1
        assert {row["metadata_json"]["contentSha256"] for row in persisted} == {
            source.content_sha256
        }
        active = next(row["metadata_json"] for row in persisted if row["is_active"])
        assert changed.input_identity is not None
        assert active["inputIdentity"] == changed.input_identity.metadata()
        assert active["inputIdentity"]["scheme"] == (
            "model-input-v1" if live_adapter else "fixture-input-v1"
        )
        conn.commit()


def test_legacy_image_hash_row_is_retained_but_cannot_claim_complete_input_match(source_document):
    document_id, image = source_document
    gateway = DeterministicVisualEmbeddingGateway(default_visual_embedding_profile(2048))
    with db_connection() as conn, conn.cursor() as cur:
        source, result = embed_source(cur, document_id, image, gateway)
        assert persist_embedding(cur, source=source, embedding=result, force_reembed=False)
        cur.execute(
            "UPDATE embeddings SET metadata_json=metadata_json-'inputIdentity' "
            "WHERE document_id=%s",
            (document_id,),
        )
        assert persist_embedding(cur, source=source, embedding=result, force_reembed=False)
        assert not persist_embedding(cur, source=source, embedding=result, force_reembed=False)
        retained = rows(cur, document_id)
        assert len(retained) == 2
        assert len([row for row in retained if row["is_active"]]) == 1
        assert any(
            "inputIdentity" not in row["metadata_json"] and not row["is_active"] for row in retained
        )
        assert persist_embedding(cur, source=source, embedding=result, force_reembed=True)
        assert len(rows(cur, document_id)) == 3
        conn.commit()


def test_query_vectors_and_missing_identity_cannot_be_persisted(source_document):
    document_id, image = source_document
    gateway = DeterministicVisualEmbeddingGateway(default_visual_embedding_profile(2048))
    with db_connection() as conn, conn.cursor() as cur:
        source, result = embed_source(cur, document_id, image, gateway)
        assert result.input_identity is not None
        for rejected in (
            replace(result, input_identity=None),
            replace(result, input_identity=replace(result.input_identity, purpose="query")),
            replace(result, text="Unrelated descriptor"),
        ):
            with pytest.raises(ValueError):
                persist_embedding(cur, source=source, embedding=rejected, force_reembed=False)
        assert rows(cur, document_id) == []
