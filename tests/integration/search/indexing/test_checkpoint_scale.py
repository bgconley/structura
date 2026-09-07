from __future__ import annotations

import json
from uuid import uuid4

import pytest

from lib.db.connection import db_connection
from lib.document_processing.authority_repository import fence_processing_attempt, lock_current_run
from lib.jobs import JobOwnershipLost, JobService
from lib.search.indexing import vector_repository
from lib.search.indexing.configuration import index_configuration
from tests.integration.search.indexing.conftest import observation


class MeasuredCursor:
    """Measure actual SQL/results while retaining real database semantics."""

    def __init__(self, cur):
        self.cur = cur
        self.calls = 0
        self.returned_bytes = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        return self.cur.execute(*args, **kwargs)

    def fetchone(self):
        row = self.cur.fetchone()
        self.measure(row)
        return row

    def fetchall(self):
        rows = self.cur.fetchall()
        for row in rows:
            self.measure(row)
        return rows

    def measure(self, row):
        if row:
            assert not {
                "structure_json",
                "inventory_json",
                "manifest_json",
                "completion_json",
            }.intersection(row)
            self.returned_bytes += len(json.dumps(row, default=str).encode())


@pytest.mark.parametrize("candidate_source", [1, 128], indirect=True)
def test_one_checkpoint_does_not_read_all_inputs_or_structural_payload(candidate_source):
    processing, run, claimed, service, _, _ = candidate_source
    config = index_configuration(model_mode="fixture", modalities=("text",))
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
        manifest = service.prepare(binding)
        with db_connection() as conn, conn.cursor() as raw:
            measured = MeasuredCursor(raw)
            vector_repository.persist_vector(
                measured, binding, observation(manifest.inputs[-1], config)
            )
            conn.commit()
        # Structural/input size increases 128x; publication remains bounded to
        # one input + model/run/header summaries, not N full-manifest projections.
        assert measured.calls <= 30
        assert measured.returned_bytes < 50_000


def test_lightweight_and_full_read_have_identical_authority_and_job_denials(candidate_source):
    processing, run, claimed, _, _, _ = candidate_source
    summaries = []
    for include in (False, True):
        with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            row = lock_current_run(cur, run.binding, include_artifacts=include)
            assert ("structure_json" in row) == include
            assert ("inventory_json" in row) == include
            summaries.append(
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"structure_json", "inventory_json"}
                }
            )
            fence_processing_attempt(cur, run.binding)
    assert summaries[0] == summaries[1]
    JobService().cancel_job(job_id=claimed.state.job_id, include_running=True, reason="test")
    for include in (False, True):
        with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            lock_current_run(cur, run.binding, include_artifacts=include)
            with pytest.raises(JobOwnershipLost):
                fence_processing_attempt(cur, run.binding)
    processing.start()
    for include in (False, True):
        with processing.scope(claimed), db_connection() as conn, conn.cursor() as cur:
            with pytest.raises(JobOwnershipLost):
                lock_current_run(cur, run.binding, include_artifacts=include)
