from __future__ import annotations

from dataclasses import replace
from threading import Event
from uuid import uuid4

import pytest

from lib.jobs.ownership import JobAttempt, job_attempt_scope
from lib.model_runtime.contracts import EmbeddingResponse
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.model_runtime.profiles import get_model_profile
from lib.search.indexing import execution
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.errors import IndexAuthorityLost, IndexCandidateError
from lib.search.indexing.model_clients import CandidateEmbeddingClients
from lib.search.indexing.models import IndexBinding, PreparedIndexSnapshot
from lib.search.indexing.projection import project_inputs
from lib.search.indexing.vectors import canonical_checkpoint
from lib.storage import ObjectStorage
from tests.unit.search.indexing.conftest import assets_for


class MemoryIndex:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.checkpoints = {}
        self.revoked = False
        self.events = []

    def load_prepared(self, binding):
        self.assert_authority(binding)
        return replace(self.snapshot, completed_input_ids=tuple(self.checkpoints))

    def assert_authority(self, binding):
        self.events.append("authority")
        if self.revoked:
            raise IndexAuthorityLost("Revoked test authority.")

    def checkpoint(self, binding, value):
        self.assert_authority(binding)
        item = next(item for item in self.snapshot.manifest.inputs if item.id == value.input_id)
        self.checkpoints[item.id] = canonical_checkpoint(value, item, self.snapshot.configuration)

    def seal(self, binding):
        self.assert_authority(binding)
        assert len(self.checkpoints) == len(self.snapshot.manifest.inputs)
        return {"inputs": len(self.checkpoints)}


class FixtureClient:
    def __init__(self, profile, service):
        self.profile = profile
        self.service = service
        self.requests = []
        self.fail_on = None
        self.response_change = {}
        self.revoke_on_response = False

    def embed(self, request):
        assert self.service.events[-1] == "authority"
        self.service.events.append("dispatch")
        self.requests.append(request)
        if self.fail_on == len(self.requests):
            raise RuntimeError("Controlled request interruption")
        if self.revoke_on_response:
            self.service.revoked = True
        return replace(
            EmbeddingResponse(
                profile_name=self.profile.name,
                model_name=self.profile.served_model_name,
                model_version="reported-fixture-version",
                dimensions=self.profile.output_dimensions,
                vectors=((0.1,) * self.profile.output_dimensions,),
                input_sha256=embedding_input_hashes(request, self.profile),
                latency_ms=5,
                identity_source="reported_model",
                artifact_revision=self.profile.embedding_protocol.artifact_revision,
            ),
            **self.response_change,
        )


def setup_execution(candidate, tmp_path):
    from lib.document_processing.models import ProcessingBinding

    config, manifest = candidate
    binding = IndexBinding(
        ProcessingBinding(uuid4(), uuid4(), manifest.parse_generation_id),
        manifest.index_generation_id,
    )
    service = MemoryIndex(PreparedIndexSnapshot(config, manifest, (), ()))
    client = FixtureClient(get_model_profile(config.space("text").profile), service)
    clients = CandidateEmbeddingClients(config.fingerprint, "fixture", client, None)
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    return binding, service, client, clients, storage


def run(binding, service, clients, storage, **kwargs):
    with job_attempt_scope(JobAttempt(uuid4(), uuid4()), Event()):
        return execution.execute_index_candidate(
            binding, service=service, clients=clients, storage=storage, **kwargs
        )


def test_bounded_resume_counts_come_from_committed_checkpoints_and_replay_makes_no_call(
    candidate, tmp_path
):
    binding, service, client, clients, storage = setup_execution(candidate, tmp_path)
    partial = run(binding, service, clients, storage, max_new_inputs=1)
    assert partial.state == "pending" and partial.counts[0].new == 1
    assert partial.counts[0].remaining == len(candidate[1].inputs) - 1
    done = run(binding, service, clients, storage)
    assert done.state == "sealed" and done.counts[0].resumed == 1
    assert done.counts[0].completed == len(candidate[1].inputs)
    count = len(client.requests)
    replay = run(binding, service, clients, storage)
    assert replay.state == "sealed" and replay.adapter_calls_started == 0
    assert replay.counts[0].new == 0 and replay.counts[0].resumed == count
    assert len(client.requests) == count
    assert replay.live_invocation_attestation == "not_evaluated"
    assert all(
        len(request.inputs) == 1 and request.purpose == "document" for request in client.requests
    )
    saved = next(iter(service.checkpoints.values())).observation
    assert saved.reported_model_version == "reported-fixture-version"
    assert saved.declared_artifact_revision == client.profile.embedding_protocol.artifact_revision
    assert saved.profile == client.profile.name and saved.model_mode == "fixture"


def test_interruption_reuses_only_completed_input_checkpoints(candidate, tmp_path):
    binding, service, client, clients, storage = setup_execution(candidate, tmp_path)
    client.fail_on = 2
    with pytest.raises(RuntimeError, match="interruption"):
        run(binding, service, clients, storage)
    assert len(service.checkpoints) == 1
    first_hash = client.requests[0].inputs[0].sha256
    client.fail_on = None
    result = run(binding, service, clients, storage)
    assert result.state == "sealed" and result.counts[0].resumed == 1
    assert sum(request.inputs[0].sha256 == first_hash for request in client.requests) == 1


def test_authority_is_rechecked_after_expensive_input_read_before_dispatch(
    candidate, tmp_path, monkeypatch
):
    binding, service, client, clients, storage = setup_execution(candidate, tmp_path)
    original = execution.verified_model_input

    def revoke_after_read(*args):
        value = original(*args)
        service.revoked = True
        return value

    monkeypatch.setattr(execution, "verified_model_input", revoke_after_read)
    with pytest.raises(IndexAuthorityLost):
        run(binding, service, clients, storage)
    assert client.requests == [] and service.checkpoints == {}


def test_revocation_during_http_refuses_response_checkpoint(candidate, tmp_path):
    binding, service, client, clients, storage = setup_execution(candidate, tmp_path)
    client.revoke_on_response = True
    with pytest.raises(IndexAuthorityLost):
        run(binding, service, clients, storage)
    assert len(client.requests) == 1 and service.checkpoints == {}


@pytest.mark.parametrize(
    "change",
    [
        {"model_name": "wrong"},
        {"artifact_revision": "wrong"},
        {"input_sha256": ("f" * 64,)},
        {"dimensions": 2048},
        {"vectors": ((0.1,) * 1024,)},
        {"identity_source": "deployment_pinned"},
    ],
)
def test_malformed_response_cannot_become_checkpoint(candidate, tmp_path, change):
    from lib.search.embedding_gateway import EmbeddingGatewayError

    binding, service, client, clients, storage = setup_execution(candidate, tmp_path)
    client.response_change = change
    with pytest.raises(EmbeddingGatewayError):
        run(binding, service, clients, storage)
    assert service.checkpoints == {}


def test_client_configuration_mismatch_fails_before_any_request(candidate, tmp_path):
    binding, service, client, clients, storage = setup_execution(candidate, tmp_path)
    with pytest.raises(IndexCandidateError, match="configuration"):
        run(binding, service, replace(clients, model_mode="live"), storage)
    assert client.requests == []


def test_visual_requests_use_exact_registered_png_and_native_dimensions(structure, tmp_path):
    from pathlib import Path

    from lib.document_processing.models import ProcessingBinding

    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    index_id = uuid4()
    assets = []
    fixture = Path(__file__).resolve().parents[3] / "fixtures/evaluation"
    for asset in assets_for(structure, index_id):
        stored = storage.store_bytes(
            (fixture / f"page-{asset.page_number}.png").read_bytes(), kind="derived", role="source"
        )
        assets.append(asset.model_copy(update={"uri": stored.uri, "byte_size": stored.byte_size}))
    config = index_configuration(model_mode="fixture", modalities=("visual",))
    manifest = project_inputs(
        structure, index_id=index_id, configuration=config, assets=tuple(assets)
    )
    binding = IndexBinding(
        ProcessingBinding(uuid4(), structure.processing_run_id, structure.parse_generation_id),
        index_id,
    )
    service = MemoryIndex(PreparedIndexSnapshot(config, manifest, tuple(assets), ()))
    client = FixtureClient(get_model_profile(config.space("visual").profile), service)
    clients = CandidateEmbeddingClients(config.fingerprint, "fixture", None, client)
    result = run(binding, service, clients, storage)
    assert result.state == "sealed" and result.counts[0].new == 2
    assert all(
        request.output_dimensions == 2048 and request.inputs[0].image_bytes
        for request in client.requests
    )
    assert client.requests[0].inputs[0].image_bytes == (fixture / "page-1.png").read_bytes()
