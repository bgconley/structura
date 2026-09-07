from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest
from psycopg.errors import RaiseException

from lib.db.connection import db_connection
from lib.document_processing.errors import CheckpointConflict, ProcessingError
from lib.document_processing.service import DocumentProcessingService
from lib.jobs import JobOwnershipLost, JobService


def test_checkpoint_replay_seal_once_and_legacy_current_selection_preserved(processing):
    run, service = processing.start(), DocumentProcessingService()
    claimed = processing.claim()
    checkpoint = processing.checkpoint(run)
    with processing.scope(claimed):
        service.initialize_inventory(run.binding, processing.inventory)
        service.initialize_inventory(run.binding, processing.inventory)
        service.checkpoint(run.binding, checkpoint)
        service.checkpoint(run.binding, checkpoint)
        assert service.load_checkpoints(run.binding) == (checkpoint,)
        structure = processing.structure(run, [checkpoint])
        digest = service.seal(run.binding, structure)
        assert service.seal(run.binding, structure) == digest
        with pytest.raises(CheckpointConflict):
            service.checkpoint(run.binding, processing.checkpoint(run, text="Changed transcript"))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state, structure_sha256 FROM document_parse_generations WHERE id = %s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone() == {"state": "sealed", "structure_sha256": digest}
        cur.execute(
            "SELECT count(*) AS n FROM document_pages WHERE document_id = %s",
            (processing.document_id,),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT canonical_asset_id FROM documents WHERE id = %s", (processing.document_id,)
        )
        assert cur.fetchone()["canonical_asset_id"] == processing.asset_id
    # Candidate readiness does not invalidate its live queue owner before ACK.
    assert (
        JobService()
        .complete_job(job_id=claimed.state.job_id, claim_token=claimed.claim_token)
        .status
        == "succeeded"
    )


def test_conflicting_source_configuration_and_content_are_rejected(processing):
    run, service = processing.start(), DocumentProcessingService()
    claimed = processing.claim()
    checkpoint = processing.checkpoint(run)
    with processing.scope(claimed):
        with pytest.raises(ProcessingError):
            service.initialize_inventory(
                run.binding, processing.inventory.model_copy(update={"original_asset_id": uuid4()})
            )
        service.initialize_inventory(run.binding, processing.inventory)
        wrong_model = replace(
            checkpoint,
            invocation=checkpoint.invocation.model_copy(update={"served_model": "wrong"}),
        )
        with pytest.raises(ProcessingError):
            service.checkpoint(run.binding, wrong_model)
        with pytest.raises(ProcessingError):
            service.checkpoint(run.binding, replace(checkpoint, raw_output="{}"))
        service.checkpoint(run.binding, checkpoint)
        with pytest.raises(CheckpointConflict):
            service.checkpoint(run.binding, processing.checkpoint(run, text="Other text"))


def test_seal_requires_committed_pages_and_exact_searchable_projection(processing):
    run, service = processing.start(), DocumentProcessingService()
    claimed = processing.claim()
    checkpoint = processing.checkpoint(run)
    structure = processing.structure(run, [checkpoint])
    with processing.scope(claimed):
        service.initialize_inventory(run.binding, processing.inventory)
        with pytest.raises(ProcessingError):
            service.seal(run.binding, structure)
        service.checkpoint(run.binding, checkpoint)
        with pytest.raises(ProcessingError):
            service.seal(run.binding, structure.model_copy(update={"chunks": ()}))
        service.seal(run.binding, structure)
    with db_connection() as conn, conn.cursor() as cur:
        with pytest.raises(RaiseException, match="immutable"):
            cur.execute(
                "UPDATE document_parse_generations SET structure_json = '{}' WHERE id = %s",
                (run.binding.parse_generation_id,),
            )
        conn.rollback()


def test_wrong_live_worker_cannot_commit_another_runs_provisional_inventory(processing):
    run, service = processing.start(), DocumentProcessingService()
    jobs = JobService()
    jobs.create_job(job_type="ingest", queue_name=f"other-{processing.queue}")
    other = jobs.claim_next_job_record(worker_name="other", queue_name=f"other-{processing.queue}")
    with processing.scope(other), pytest.raises(JobOwnershipLost):
        service.initialize_inventory(run.binding, processing.inventory)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT inventory_json FROM document_parse_generations WHERE id = %s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone()["inventory_json"] is None
    with pytest.raises(JobOwnershipLost):
        service.initialize_inventory(run.binding, processing.inventory)


def test_cancelled_claim_rolls_back_checkpoint_write_in_same_transaction(processing):
    run, service = processing.start(), DocumentProcessingService()
    claimed = processing.claim()
    with processing.scope(claimed):
        service.initialize_inventory(run.binding, processing.inventory)
    JobService().cancel_job(
        job_id=claimed.state.job_id, reason="Cancel candidate", include_running=True
    )
    with processing.scope(claimed), pytest.raises(JobOwnershipLost):
        service.checkpoint(run.binding, processing.checkpoint(run))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id = %s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 0


def test_history_cannot_be_deleted_independently_of_document(processing):
    run, service = processing.start(), DocumentProcessingService()
    claimed = processing.claim()
    with processing.scope(claimed):
        service.initialize_inventory(run.binding, processing.inventory)
        service.checkpoint(run.binding, processing.checkpoint(run))
    with db_connection() as conn, conn.cursor() as cur:
        with pytest.raises(RaiseException, match="retained"):
            cur.execute(
                "DELETE FROM document_parse_page_checkpoints WHERE parse_generation_id = %s",
                (run.binding.parse_generation_id,),
            )
        conn.rollback()
        cur.execute("DELETE FROM documents WHERE id = %s", (processing.document_id,))
        conn.commit()
