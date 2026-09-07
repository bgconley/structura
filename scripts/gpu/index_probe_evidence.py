"""Exact hidden-generation evidence for an isolated synthetic indexing probe.

This is a diagnostic reader, not an application search or authorization adapter.
It refuses every database except the disposable integration-test namespace.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

import httpx

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.document_processing.models import content_digest
from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.models import IndexBinding, IndexInput, IndexManifest, VectorObservation
from lib.search.indexing.vectors import canonical_checkpoint
from scripts.gpu.probe_database import assert_isolated_connection, isolated_database_name


class ObservedTransport(httpx.BaseTransport):
    """Count actual HTTP attempts without capturing URLs, headers or input bytes."""

    def __init__(self) -> None:
        self.started = 0
        self.responses = 0
        self.transport = httpx.HTTPTransport(retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.started += 1
        response = self.transport.handle_request(request)
        self.responses += 1
        return response

    def close(self) -> None:
        self.transport.close()


@dataclass(frozen=True)
class PersistedProbeVector:
    input_id: UUID
    modality: str
    page_number: int
    model_input_sha256: str
    vector_sha256: str
    checkpoint_sha256: str
    values: tuple[float, ...]


def capture_index_vectors(
    binding: IndexBinding, manifest: IndexManifest, configuration: IndexConfiguration
) -> tuple[dict[str, Any], tuple[PersistedProbeVector, ...]]:
    """Rehash actual pgvector values and immutable observations in one DB snapshot."""
    database_url = get_settings().database_url
    expected_database = isolated_database_name(database_url)
    with db_connection(database_url, connect_timeout=5) as conn, conn.cursor() as cur:
        assert_isolated_connection(conn, expected_database)
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cur.execute("SET LOCAL statement_timeout='10s'")
        cur.execute(
            "SELECT config_sha256,manifest_json,manifest_sha256,completion_json,completion_sha256 "
            "FROM document_index_generations WHERE id=%s AND document_id=%s "
            "AND processing_run_id=%s AND parse_generation_id=%s AND state='sealed'",
            (
                binding.index_generation_id,
                binding.processing.document_id,
                binding.processing.processing_run_id,
                binding.processing.parse_generation_id,
            ),
        )
        header = cur.fetchone()
        if (
            header is None
            or header["config_sha256"] != configuration.fingerprint
            or header["manifest_json"] != manifest.model_dump(mode="json")
            or header["manifest_sha256"] != manifest.fingerprint
            or content_digest(header["completion_json"]) != header["completion_sha256"]
        ):
            raise RuntimeError("Probe index is not the exact sealed generation requested.")
        cur.execute(
            "SELECT i.input_json,v.observation_json,v.embedding::text AS vector_text,"
            "v.vector_sha256,v.content_sha256 FROM document_index_inputs i "
            "JOIN document_index_vector_checkpoints v ON v.input_id=i.id "
            "AND v.index_generation_id=i.index_generation_id "
            "WHERE i.index_generation_id=%s ORDER BY i.ordinal",
            (binding.index_generation_id,),
        )
        rows = cur.fetchall()
    if len(rows) != len(manifest.inputs):
        raise RuntimeError("Probe index has an incomplete persisted vector inventory.")
    vectors = []
    observations = []
    for expected, row in zip(manifest.inputs, rows, strict=True):
        item = IndexInput.model_validate(row["input_json"])
        observation = VectorObservation.model_validate(row["observation_json"])
        observed = canonical_checkpoint(observation, item, configuration)
        persisted = canonical_checkpoint(
            observation.model_copy(update={"values": tuple(json.loads(row["vector_text"]))}),
            item,
            configuration,
        )
        if (
            item != expected
            or observed.vector_sha256 != persisted.vector_sha256
            or persisted.vector_sha256 != row["vector_sha256"]
            or observed.content_sha256 != row["content_sha256"]
        ):
            raise RuntimeError("Probe vector bytes differ from their immutable checkpoints.")
        vectors.append(
            PersistedProbeVector(
                item.id,
                item.modality,
                item.page_number,
                item.model_input_sha256,
                persisted.vector_sha256,
                observed.content_sha256,
                persisted.observation.values,
            )
        )
        observations.append(observed.observation.model_dump(mode="json"))
    expected_completion = [
        {
            "input_id": str(vector.input_id),
            "content_sha256": vector.checkpoint_sha256,
            "vector_sha256": vector.vector_sha256,
        }
        for vector in vectors
    ]
    if header["completion_json"]["vectors"] != expected_completion:
        raise RuntimeError("Probe completion does not bind the captured vector inventory.")
    evidence = {
        "index_generation_id": str(binding.index_generation_id),
        "processing_run_id": str(binding.processing.processing_run_id),
        "parse_generation_id": str(binding.processing.parse_generation_id),
        "configuration": configuration.model_dump(mode="json"),
        "manifest": manifest.model_dump(mode="json"),
        "completion": header["completion_json"],
        "completion_sha256": header["completion_sha256"],
        "vectors": [asdict(vector) for vector in vectors],
        # Retain all validated provenance so the protected bundle can reproduce
        # checkpoint hashes independently of this live database reader.
        "observations": observations,
    }
    return evidence, tuple(vectors)
