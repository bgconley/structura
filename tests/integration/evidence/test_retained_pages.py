from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg.errors import ForeignKeyViolation, RaiseException

from lib.db.connection import db_connection
from lib.document_processing.service import DocumentProcessingService
from lib.evidence.errors import EvidenceConflict, EvidenceUnavailable
from lib.evidence.read_repository import read_generation
from lib.evidence.read_service import GenerationEvidenceReader
from lib.jobs import JobOwnershipLost
from lib.storage import cleanup_unreferenced_stored_object
from tests.integration.evidence.conftest import populate


def test_all_page_catalog_is_independent_of_embedding_eligibility_and_idempotent(evidence):
    processing, run, claimed, writer, binding, asset, stored = evidence
    reader = GenerationEvidenceReader(writer.storage)
    manifest = reader.manifest(
        processing.document_id, run.binding.parse_generation_id, processing.access
    )
    assert manifest.total == 1 and manifest.pages[0].render_registration == "not_retained"
    with processing.scope(claimed):
        with pytest.raises(EvidenceConflict, match="incomplete"):
            writer.seal(binding)
        assert writer.start(run.binding) == binding
        assert writer.checkpoint(binding, asset) == writer.checkpoint(binding, asset)
        assert writer.seal(binding) == writer.seal(binding)
    manifest = reader.manifest(
        processing.document_id, run.binding.parse_generation_id, processing.access
    )
    assert (
        manifest.render_set_state == "sealed"
        and manifest.pages[0].render_registration == "registered"
    )
    assert (
        b"".join(
            reader.render(
                processing.document_id, run.binding.parse_generation_id, 1, processing.access
            ).chunks()
        )
        == stored.path.read_bytes()
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_index_generations WHERE document_id=%s",
            (processing.document_id,),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT count(*) AS n FROM document_pages WHERE document_id=%s",
            (processing.document_id,),
        )
        assert cur.fetchone()["n"] == 0
    # Compact page read excludes full structure/inventory and raw model response.
    row = read_generation(
        processing.document_id, run.binding.parse_generation_id, processing.access
    )
    assert "structure_json" not in row and "inventory_json" not in row
    assert row["pages"][0]["raw_output"] is None and row["pages"][0]["page_json"] is None
    page = reader.page(
        processing.document_id, run.binding.parse_generation_id, 1, processing.access
    )
    assert page.page.id == asset.page_id and page.chunks[0].page_number == 1


@pytest.mark.parametrize("transition", ["supersede", "cancel"])
def test_history_remains_readable_but_no_longer_writable(evidence, transition):
    processing, run, claimed, writer, binding, asset, _ = evidence
    populate(evidence)
    if transition == "supersede":
        processing.start()
    else:
        DocumentProcessingService().cancel(run.binding, processing.access)
    reader = GenerationEvidenceReader(writer.storage)
    assert (
        reader.page(
            processing.document_id, run.binding.parse_generation_id, 1, processing.access
        ).page.id
        == asset.page_id
    )
    with processing.scope(claimed), pytest.raises(JobOwnershipLost):
        writer.checkpoint(binding, asset)
    with pytest.raises(EvidenceUnavailable):
        reader.page(uuid4(), run.binding.parse_generation_id, 1, processing.access)
    with pytest.raises(EvidenceUnavailable):
        reader.page(processing.document_id, uuid4(), 1, processing.access)
    with pytest.raises(EvidenceUnavailable):
        reader.page(processing.document_id, run.binding.parse_generation_id, 2, processing.access)


def test_missing_bytes_after_checkpoint_prevent_seal(evidence):
    processing, _, claimed, writer, binding, asset, stored = evidence
    with processing.scope(claimed):
        writer.checkpoint(binding, asset)
        stored.path.unlink()
        with pytest.raises(EvidenceUnavailable):
            writer.seal(binding)
        assert writer.snapshot(binding).state == "building"


@pytest.mark.parametrize("target", ["original", "producer", "set", "page"])
def test_independent_source_and_history_deletion_cannot_commit(evidence, target):
    processing, _, claimed, _, binding, asset, _ = evidence
    populate(evidence)
    statements = {
        "original": ("DELETE FROM document_assets WHERE id=%s", processing.asset_id),
        "producer": ("DELETE FROM pipeline_jobs WHERE id=%s", claimed.state.job_id),
        "set": ("DELETE FROM document_parse_render_sets WHERE id=%s", binding.render_set_id),
        "page": ("DELETE FROM document_parse_page_render_assets WHERE id=%s", asset.id),
    }
    statement, identity = statements[target]
    with (
        pytest.raises((ForeignKeyViolation, RaiseException)),
        db_connection() as conn,
        conn.cursor() as cur,
    ):
        cur.execute(statement, (identity,))
        conn.commit()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_render_assets WHERE id=%s", (asset.id,)
        )
        assert cur.fetchone()["n"] == 1


def test_document_cascade_and_shared_content_cleanup_retention(evidence):
    processing, _, _, writer, binding, _, stored = evidence
    populate(evidence)
    cleanup_unreferenced_stored_object(stored)
    assert stored.path.exists()
    shared = writer.storage.store_bytes(
        stored.path.read_bytes(), kind="derived", role="another-role"
    )
    cleanup_unreferenced_stored_object(shared)
    assert shared.path.exists()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id=%s", (processing.document_id,))
        conn.commit()
    cleanup_unreferenced_stored_object(stored)
    cleanup_unreferenced_stored_object(shared)
    assert not stored.path.exists() and not shared.path.exists()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_render_sets WHERE id=%s",
            (binding.render_set_id,),
        )
        assert cur.fetchone()["n"] == 0


def test_document_cascade_coexists_with_populated_index_catalog(evidence, candidate_source):
    from lib.search.indexing.configuration import index_configuration
    from tests.integration.search.indexing.conftest import asset_for, observation

    processing, run, claimed, index, checkpoint, stored = candidate_source
    config = index_configuration(model_mode="fixture")
    with processing.scope(claimed):
        binding = index.start(run.binding, request_key=uuid4(), configuration=config)
        manifest = index.prepare(binding, (asset_for(binding, checkpoint, stored),))
        for item in manifest.inputs:
            index.checkpoint(binding, observation(item, config))
        index.seal(binding)
    populate(evidence)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id=%s", (processing.document_id,))
        conn.commit()
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_render_assets "
            "WHERE parse_generation_id=%s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT count(*) AS n FROM document_index_vector_checkpoints "
            "WHERE index_generation_id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone()["n"] == 0
    cleanup_unreferenced_stored_object(stored)
    assert not stored.path.exists()
