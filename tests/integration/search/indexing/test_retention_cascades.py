from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.errors import ForeignKeyViolation, RaiseException

from lib.db.connection import db_connection
from lib.search.indexing.configuration import index_configuration
from tests.integration.search.indexing.conftest import asset_for, observation

EDGES = (
    ("document_processing_runs", "document_assets"),
    ("document_index_generations", "document_processing_runs"),
    ("document_index_generations", "pipeline_jobs"),
    ("document_generation_render_assets", "document_assets"),
    ("document_generation_render_assets", "document_parse_page_checkpoints"),
    ("document_index_inputs", "document_generation_render_assets"),
)


def populated(candidate_source):
    processing, run, claimed, service, checkpoint, stored = candidate_source
    config = index_configuration(model_mode="fixture")
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
        manifest = service.prepare(binding, (asset_for(binding, checkpoint, stored),))
        for item in manifest.inputs:
            service.checkpoint(binding, observation(item, config))
        service.seal(binding)
    return processing, run, claimed, binding


def test_reviewed_cross_branch_edges_are_deferred_no_action(candidate_source):
    with db_connection() as conn, conn.cursor() as cur:
        for child, parent in EDGES:
            cur.execute(
                "SELECT confdeltype,condeferrable,condeferred FROM pg_constraint "
                "WHERE contype='f' AND conrelid=%s::regclass AND confrelid=%s::regclass",
                (child, parent),
            )
            assert cur.fetchall() == [
                {"confdeltype": "a", "condeferrable": True, "condeferred": True}
            ]


@pytest.mark.parametrize("parent", ["original", "producer"])
def test_independent_parent_deletion_fails_at_commit_and_preserves_all_history(
    candidate_source, parent
):
    processing, run, claimed, binding = populated(candidate_source)
    table, identity = (
        ("document_assets", processing.asset_id)
        if parent == "original"
        else ("pipeline_jobs", claimed.state.job_id)
    )
    with db_connection() as conn, conn.cursor() as cur:
        # A fixed two-table choice is identifier-quoted; the row ID is bound.
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
        cur.execute(
            sql.SQL("DELETE FROM {} WHERE id=%s").format(sql.Identifier(table)), (identity,)
        )
        # DELETE itself is permitted; it may not commit while retained dependants exist.
        with pytest.raises(ForeignKeyViolation):
            conn.commit()
        conn.rollback()
    with db_connection() as conn, conn.cursor() as cur:
        # Same fixed identifier and bound row ID as the attempted deletion.
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
        cur.execute(
            sql.SQL("SELECT id FROM {} WHERE id=%s").format(sql.Identifier(table)), (identity,)
        )
        assert cur.fetchone()["id"] == identity
        cur.execute(
            "SELECT state,completion_json FROM document_index_generations WHERE id=%s",
            (binding.index_generation_id,),
        )
        row = cur.fetchone()
        assert row["state"] == "sealed" and row["completion_json"]["input_count"] == 2
        cur.execute(
            "SELECT count(*) AS n FROM document_index_vector_checkpoints "
            "WHERE index_generation_id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone()["n"] == 2
        cur.execute(
            "SELECT status FROM document_processing_runs WHERE id=%s",
            (run.binding.processing_run_id,),
        )
        assert cur.fetchone()["status"] == "sealed"


@pytest.mark.parametrize(
    "table,identifier",
    [
        ("document_processing_runs", "processing_run_id"),
        ("document_parse_generations", "parse_generation_id"),
        ("document_generation_render_assets", "index_generation_id"),
        ("document_index_inputs", "index_generation_id"),
        ("document_index_vector_checkpoints", "index_generation_id"),
    ],
)
def test_individual_history_rows_remain_protected_by_retention_triggers(
    candidate_source, table, identifier
):
    _, run, _, binding = populated(candidate_source)
    identity = getattr(binding, identifier, None) or getattr(run.binding, identifier)
    column = (
        "id" if table in {"document_processing_runs", "document_parse_generations"} else identifier
    )
    with pytest.raises(RaiseException), db_connection() as conn, conn.cursor() as cur:
        # Parametrized test literals are identifier-quoted; the row ID is bound.
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
        cur.execute(
            sql.SQL("DELETE FROM {} WHERE {}=%s").format(
                sql.Identifier(table), sql.Identifier(column)
            ),
            (identity,),
        )
