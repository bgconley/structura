from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg.errors import RaiseException

from lib.db.connection import db_connection
from lib.jobs import JobOwnershipLost
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.errors import IndexCheckpointConflict
from lib.storage import cleanup_unreferenced_stored_object
from tests.integration.search.indexing.conftest import asset_for, observation


def test_exact_manifest_resume_float32_seal_and_no_legacy_publication(candidate_source):
    processing, run, claimed, service, checkpoint, stored = candidate_source
    config = index_configuration(model_mode="fixture")
    key = uuid4()
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=key, configuration=config)
        assert service.start(run.binding, request_key=key, configuration=config) == binding
        asset = asset_for(binding, checkpoint, stored)
        manifest = service.prepare(binding, (asset,))
        assert service.prepare(binding, (asset,)) == manifest
        assert {i.modality for i in manifest.inputs} == {"text", "visual"}
        with pytest.raises(IndexCheckpointConflict, match="missing"):
            service.seal(binding)
        for item in manifest.inputs:
            value = observation(item, config)
            digest = service.checkpoint(binding, value)
            assert service.checkpoint(binding, value) == digest
            with pytest.raises(IndexCheckpointConflict, match="different"):
                service.checkpoint(binding, value.model_copy(update={"invocation_id": uuid4()}))
        assert service.missing_inputs(binding) == ()
        completion = service.seal(binding)
        assert service.seal(binding) == completion
        assert completion["input_count"] == 2
        assert completion["live_invocation_attestation"] == "not_evaluated"
        assert completion["fact_basis"] == completion["metadata_basis"] == "not_collected"
    cleanup_unreferenced_stored_object(stored)
    assert stored.path.exists()
    same_hash_other_uri = service.storage.store_bytes(
        stored.path.read_bytes(), kind="derived", role="other-role"
    )
    cleanup_unreferenced_stored_object(same_hash_other_uri)
    assert same_hash_other_uri.path.exists()
    orphan = service.storage.store_bytes(b"unreferenced orphan", kind="derived", role="orphan")
    cleanup_unreferenced_stored_object(orphan)
    assert not orphan.path.exists()
    with db_connection() as conn, conn.cursor() as cur:
        for table in ("document_pages", "document_elements", "document_chunks", "embeddings"):
            # Fixed local table names only; prove the hidden lane publishes none.
            from psycopg import sql

            cur.execute(
                sql.SQL("SELECT count(*) AS n FROM {} WHERE document_id=%s").format(
                    sql.Identifier(table)
                ),
                (processing.document_id,),
            )
            assert cur.fetchone()["n"] == 0


def test_superseded_build_and_cancelled_successor_never_revive_old_slot(candidate_source):
    processing, run, claimed, service, _, _ = candidate_source
    config = index_configuration(model_mode="fixture", modalities=("text",))
    with processing.scope(claimed):
        key = uuid4()
        first = service.start(run.binding, request_key=key, configuration=config)
        manifest = service.prepare(first)
        second = service.start(run.binding, request_key=uuid4(), configuration=config)
        for operation in (
            lambda: service.checkpoint(first, observation(manifest.inputs[0], config)),
            lambda: service.start(run.binding, request_key=key, configuration=config),
            lambda: service.seal(first),
        ):
            with pytest.raises(JobOwnershipLost):
                operation()
        service.cancel(second)
        with pytest.raises(JobOwnershipLost):
            service.prepare(first)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT generation,revoked_at FROM document_index_generations WHERE "
            "document_id=%s ORDER BY generation",
            (processing.document_id,),
        )
        rows = cur.fetchall()
        assert [r["generation"] for r in rows] == [1, 2]
        assert all(r["revoked_at"] for r in rows)
        cur.execute(
            "SELECT status,claim_token FROM pipeline_jobs WHERE id=%s", (claimed.state.job_id,)
        )
        assert cur.fetchone() == {"status": "running", "claim_token": claimed.claim_token}


def test_independent_new_processing_run_rejects_live_old_index_producer(candidate_source):
    processing, run, claimed, service, _, _ = candidate_source
    config = index_configuration(model_mode="fixture", modalities=("text",))
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
        manifest = service.prepare(binding)
    processing.start()
    with processing.scope(claimed), pytest.raises(JobOwnershipLost):
        service.checkpoint(binding, observation(manifest.inputs[0], config))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_index_vector_checkpoints WHERE "
            "index_generation_id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone()["n"] == 0


def test_immutable_storage_and_complete_document_cascade(candidate_source):
    processing, run, claimed, service, checkpoint, stored = candidate_source
    config = index_configuration(model_mode="fixture")
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
        manifest = service.prepare(binding, (asset_for(binding, checkpoint, stored),))
        for item in manifest.inputs:
            service.checkpoint(binding, observation(item, config))
        service.seal(binding)
    statements = (
        (
            "UPDATE document_index_generations SET config_sha256=%s WHERE id=%s",
            ("f" * 64, binding.index_generation_id),
        ),
        (
            "UPDATE document_index_inputs SET input_json='{}' WHERE index_generation_id=%s",
            (binding.index_generation_id,),
        ),
        (
            "UPDATE document_index_vector_checkpoints SET observation_json='{}' WHERE "
            "index_generation_id=%s",
            (binding.index_generation_id,),
        ),
        ("DELETE FROM document_index_generations WHERE id=%s", (binding.index_generation_id,)),
    )
    for statement, params in statements:
        with pytest.raises(RaiseException), db_connection() as conn, conn.cursor() as cur:
            cur.execute(statement, params)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id=%s", (processing.document_id,))
        conn.commit()
    cleanup_unreferenced_stored_object(stored)
    assert not stored.path.exists()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_index_generations WHERE id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT count(*) AS n FROM document_index_vector_checkpoints WHERE "
            "index_generation_id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone()["n"] == 0


def test_missing_render_refuses_preparation_and_vector_publication(candidate_source):
    processing, run, claimed, service, checkpoint, stored = candidate_source
    config = index_configuration(model_mode="fixture", modalities=("visual",))
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
        asset = asset_for(binding, checkpoint, stored)
        manifest = service.prepare(binding, (asset,))
        stored.path.unlink()
        from lib.search.indexing.errors import IndexCandidateError

        with pytest.raises(IndexCandidateError, match="unavailable"):
            service.checkpoint(binding, observation(manifest.inputs[0], config))
        with pytest.raises(IndexCandidateError, match="unavailable"):
            service.seal(binding)


def test_unscoped_caller_cannot_publish_even_with_exact_ids(candidate_source):
    _, run, _, service, _, _ = candidate_source
    with pytest.raises(JobOwnershipLost):
        service.start(
            run.binding,
            request_key=uuid4(),
            configuration=index_configuration(model_mode="fixture"),
        )


@pytest.mark.parametrize("candidate_source", [0], indirect=True)
def test_zero_text_eligibility_seals_with_explicit_page_denominator(candidate_source):
    processing, run, claimed, service, _, _ = candidate_source
    with processing.scope(claimed):
        binding = service.start(
            run.binding,
            request_key=uuid4(),
            configuration=index_configuration(model_mode="fixture", modalities=("text",)),
        )
        manifest = service.prepare(binding)
        assert manifest.inputs == () and len(manifest.pages) == 1
        assert manifest.pages[0].text == "ineligible"
        completion = service.seal(binding)
        assert completion["input_count"] == 0 and completion["page_count"] == 1
        assert completion["modalities"] == [{"modality": "text", "eligible": 0, "completed": 0}]


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_seal_reverifies_render_after_completed_vector(candidate_source, damage):
    processing, run, claimed, service, checkpoint, stored = candidate_source
    config = index_configuration(model_mode="fixture", modalities=("visual",))
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
        manifest = service.prepare(binding, (asset_for(binding, checkpoint, stored),))
        service.checkpoint(binding, observation(manifest.inputs[0], config))
        assert service.missing_inputs(binding) == ()
        if damage == "missing":
            stored.path.unlink()
        else:
            stored.path.write_bytes(b"changed after checkpoint")
        from lib.search.indexing.errors import IndexCandidateError

        with pytest.raises(IndexCandidateError):
            service.seal(binding)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state,completion_json FROM document_index_generations WHERE id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone() == {"state": "embedding", "completion_json": None}
