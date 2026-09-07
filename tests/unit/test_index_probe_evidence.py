from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from lib.config import Settings
from lib.document_parsing.structure import DocumentStructure
from lib.document_processing.models import ProcessingBinding, content_digest
from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.model_runtime.profiles import get_model_profile
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.models import IndexBinding, VectorObservation
from lib.search.indexing.projection import project_inputs
from lib.search.indexing.vectors import canonical_checkpoint
from scripts.gpu import index_probe_evidence, probe_persisted_index


def evidence_fixture(monkeypatch):
    config = index_configuration(model_mode="fixture", modalities=("text",))
    capture = Path(__file__).resolve().parents[1] / "fixtures/evaluation/capture.json"
    structure = DocumentStructure.model_validate(json.loads(capture.read_text())["structure"])
    index_id = uuid4()
    manifest = project_inputs(structure, index_id=index_id, configuration=config)
    binding = IndexBinding(
        ProcessingBinding(uuid4(), structure.processing_run_id, structure.parse_generation_id),
        index_id,
    )
    rows, completion_vectors = [], []
    space = config.space("text")
    for item in manifest.inputs:
        checkpoint = canonical_checkpoint(
            VectorObservation(
                input_id=item.id,
                model_input_sha256=item.model_input_sha256,
                values=(0.1,) * space.dimensions,
                profile=space.profile,
                reported_model=space.served_model,
                reported_model_version="controlled-reported-version",
                declared_artifact_revision=space.protocol.artifact_revision,
                model_mode="fixture",
                invocation_id=uuid4(),
                latency_ms=5,
            ),
            item,
            config,
        )
        rows.append(
            {
                "input_json": item.model_dump(mode="json"),
                "observation_json": checkpoint.observation.model_dump(mode="json"),
                "vector_text": json.dumps(checkpoint.observation.values),
                "vector_sha256": checkpoint.vector_sha256,
                "content_sha256": checkpoint.content_sha256,
            }
        )
        completion_vectors.append(
            {
                "input_id": str(item.id),
                "content_sha256": checkpoint.content_sha256,
                "vector_sha256": checkpoint.vector_sha256,
            }
        )
    completion = {"vectors": completion_vectors}
    header = {
        "config_sha256": config.fingerprint,
        "manifest_json": manifest.model_dump(mode="json"),
        "manifest_sha256": manifest.fingerprint,
        "completion_json": completion,
        "completion_sha256": content_digest(completion),
    }

    @contextmanager
    def cursor():
        yield SimpleNamespace(
            execute=lambda *args: None, fetchone=lambda: header, fetchall=lambda: rows
        )

    @contextmanager
    def connection(*args, **kwargs):
        yield SimpleNamespace(
            cursor=cursor, info=SimpleNamespace(dbname="structura_it_0123456789abcdef")
        )

    monkeypatch.setattr(index_probe_evidence, "db_connection", connection)
    monkeypatch.setattr(
        index_probe_evidence,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql://localhost/structura_it_0123456789abcdef"
        ),
    )
    return config, binding, manifest, rows


def test_private_capture_contains_full_independently_recomputable_checkpoint_provenance(
    monkeypatch,
):
    config, binding, manifest, _ = evidence_fixture(monkeypatch)
    evidence, vectors = index_probe_evidence.capture_index_vectors(binding, manifest, config)
    assert len(evidence["observations"]) == len(vectors) == len(manifest.inputs)
    for item, observation, vector in zip(
        manifest.inputs, evidence["observations"], vectors, strict=True
    ):
        reconstructed = canonical_checkpoint(
            VectorObservation.model_validate(observation), item, config
        )
        assert reconstructed.observation.reported_model_version == "controlled-reported-version"
        assert reconstructed.content_sha256 == vector.checkpoint_sha256
        assert reconstructed.vector_sha256 == vector.vector_sha256
        assert reconstructed.observation.values == vector.values


@pytest.mark.parametrize("damage", ["vector", "identity", "checkpoint"])
def test_capture_refuses_corrupt_persisted_vector_or_provenance(monkeypatch, damage):
    config, binding, manifest, rows = evidence_fixture(monkeypatch)
    if damage == "vector":
        rows[0]["vector_text"] = json.dumps([0.2] * 1536)
    elif damage == "identity":
        rows[0]["observation_json"]["reported_model_version"] = "changed"
    else:
        rows[0]["content_sha256"] = "f" * 64
    with pytest.raises(RuntimeError, match="immutable checkpoints"):
        index_probe_evidence.capture_index_vectors(binding, manifest, config)


def test_query_evidence_observes_actual_protocol_requests_and_preserves_identity(monkeypatch):
    config = index_configuration(model_mode="live")
    calls = []

    def respond(request):
        payload = json.loads(request.content)
        visual = "messages" in payload
        calls.append(payload)
        return httpx.Response(
            200,
            json={
                "model": payload["model"],
                "model_version": "controlled-query-version",
                "data": [
                    {"index": i, "embedding": [0.1] * (2048 if visual else 1536)}
                    for i in range(1 if visual else len(payload["input"]))
                ],
            },
        )

    def transport():
        observed = index_probe_evidence.ObservedTransport()
        observed.transport.close()
        observed.transport = httpx.MockTransport(respond)
        return observed

    monkeypatch.setattr(probe_persisted_index, "ObservedTransport", transport)
    vectors = tuple(
        index_probe_evidence.PersistedProbeVector(
            uuid4(),
            modality,
            1,
            "a" * 64,
            "b" * 64,
            "c" * 64,
            (0.1,) * config.space(modality).dimensions,
        )
        for modality in config.modalities
    )
    evidence = probe_persisted_index.query_persisted_vectors(
        vectors,
        config,
        Settings(
            _env_file=None,
            model_mode="live",
            model_text_embed_url="http://text.example",
            model_visual_embed_url="http://visual.example",
        ),
    )
    assert len(calls) == 3  # One text batch and two native visual-message queries.
    assert [m["actual_http_attempts"] for m in evidence["modalities"]] == [1, 2]
    assert all(
        m["actual_http_responses"] == m["actual_http_attempts"] for m in evidence["modalities"]
    )
    assert all(
        m["reported_model_version"] == "controlled-query-version" for m in evidence["modalities"]
    )
    assert all(m["identity_source"] == "reported_model" for m in evidence["modalities"])
    for modality in config.modalities:
        profile = get_model_profile(config.space(modality).profile)
        request = EmbeddingRequest(
            profile_name=profile.name,
            inputs=tuple(EmbeddingInput(text=text) for text, _ in probe_persisted_index.QUERIES),
            output_dimensions=profile.output_dimensions,
            timeout_seconds=90,
            purpose="query",
        )
        measurements = [m for m in evidence["measurements"] if m["modality"] == modality]
        assert tuple(m["query_input_sha256"] for m in measurements) == embedding_input_hashes(
            request, profile
        )
        assert all(m["purpose"] == "query" for m in measurements)
