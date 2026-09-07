from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from lib.db.connection import db_connection
from lib.jobs import JobOwnershipLost, JobService
from lib.model_runtime.contracts import EmbeddingResponse
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.model_runtime.profiles import get_model_profile
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.execution import execute_index_candidate
from lib.search.indexing.model_clients import CandidateEmbeddingClients


class ControlledEmbeddingClient:
    """Full adapter contract with controlled output; never live invocation evidence."""

    def __init__(self, profile):
        self.profile = profile
        self.requests = []
        self.entered = Event()
        self.release = Event()
        self.block = False

    def embed(self, request):
        self.requests.append(request)
        if self.block:
            self.entered.set()
            assert self.release.wait(timeout=10), "Controlled inference was not released"
        return EmbeddingResponse(
            profile_name=self.profile.name,
            model_name=self.profile.served_model_name,
            model_version="controlled-fixture-version",
            dimensions=self.profile.output_dimensions,
            vectors=((0.1,) * self.profile.output_dimensions,),
            input_sha256=embedding_input_hashes(request, self.profile),
            latency_ms=1,
            identity_source="reported_model",
            artifact_revision=self.profile.embedding_protocol.artifact_revision,
        )


def setup_execution(candidate_source):
    processing, run, claimed, service, _, _ = candidate_source
    config = index_configuration(model_mode="fixture", modalities=("text",))
    with processing.scope(claimed):
        binding = service.start(run.binding, request_key=uuid4(), configuration=config)
        service.prepare(binding)
    client = ControlledEmbeddingClient(get_model_profile(config.space("text").profile))
    clients = CandidateEmbeddingClients(config.fingerprint, "fixture", client, None)
    return processing, claimed, service, binding, client, clients


@pytest.mark.parametrize("candidate_source", [3], indirect=True)
def test_real_checkpoint_resume_seal_and_no_implicit_job_ack(candidate_source):
    processing, claimed, service, binding, client, clients = setup_execution(candidate_source)
    with processing.scope(claimed):
        partial = execute_index_candidate(
            binding, clients=clients, storage=service.storage, service=service, max_new_inputs=1
        )
        assert partial.state == "pending"
        assert (partial.counts[0].eligible, partial.counts[0].remaining) == (3, 2)
        done = execute_index_candidate(
            binding, clients=clients, storage=service.storage, service=service
        )
        assert done.state == "sealed"
        assert (done.counts[0].new, done.counts[0].resumed, done.counts[0].remaining) == (2, 1, 0)
        replay = execute_index_candidate(
            binding, clients=clients, storage=service.storage, service=service
        )
        assert replay.completion_sha256 == done.completion_sha256
        assert replay.adapter_calls_started == replay.adapter_calls_completed == 0
        assert (replay.counts[0].completed, replay.counts[0].new) == (3, 0)
    assert len(client.requests) == 3
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT observation_json FROM document_index_vector_checkpoints "
            "WHERE index_generation_id=%s",
            (binding.index_generation_id,),
        )
        observations = [row["observation_json"] for row in cur.fetchall()]
        assert len(observations) == 3
        assert all(value["model_mode"] == "fixture" for value in observations)
        assert all(
            value["reported_model_version"] == "controlled-fixture-version"
            and value["declared_artifact_revision"]
            == client.profile.embedding_protocol.artifact_revision
            for value in observations
        )
        cur.execute(
            "SELECT status,claim_token FROM pipeline_jobs WHERE id=%s", (claimed.state.job_id,)
        )
        assert cur.fetchone() == {"status": "running", "claim_token": claimed.claim_token}


@pytest.mark.parametrize("revocation", ["job", "processing_run", "index"])
def test_independent_revocation_during_inference_commits_then_rejects_response(
    candidate_source, revocation
):
    processing, claimed, service, binding, client, clients = setup_execution(candidate_source)
    client.block = True

    def execute():
        with processing.scope(claimed):
            return execute_index_candidate(
                binding, clients=clients, storage=service.storage, service=service
            )

    def revoke():
        if revocation == "job":
            JobService().cancel_job(
                job_id=claimed.state.job_id,
                household_id=processing.access.household_id,
                reason="controlled cancellation",
                include_running=True,
            )
        elif revocation == "processing_run":
            processing.start()
        else:
            with processing.scope(claimed):
                service.cancel(binding)

    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(execute)
        try:
            assert client.entered.wait(timeout=5)
            # This separate DB connection must commit while HTTP is blocked.
            # Holding document/run/job/index locks over inference would deadlock.
            pool.submit(revoke).result(timeout=5)
        finally:
            client.release.set()
        with pytest.raises(JobOwnershipLost):
            running.result(timeout=5)
    assert len(client.requests) == 1
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_index_vector_checkpoints "
            "WHERE index_generation_id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT completion_json,sealed_at FROM document_index_generations WHERE id=%s",
            (binding.index_generation_id,),
        )
        assert cur.fetchone() == {"completion_json": None, "sealed_at": None}


@pytest.mark.parametrize("candidate_source", [0], indirect=True)
def test_zero_eligibility_seals_from_persisted_denominator_without_dispatch(candidate_source):
    processing, claimed, service, binding, client, clients = setup_execution(candidate_source)
    with processing.scope(claimed):
        result = execute_index_candidate(
            binding, clients=clients, storage=service.storage, service=service
        )
        snapshot = service.load_prepared(binding)
    assert result.state == "sealed" and result.adapter_calls_started == 0
    assert result.counts[0].eligible == result.counts[0].completed == 0
    assert client.requests == []
    assert len(snapshot.manifest.pages) == 1
    assert snapshot.manifest.pages[0].text == "ineligible"
