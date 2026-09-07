"""Insert-or-verify float32 checkpoints and seal only the complete frozen input set."""

from __future__ import annotations

import json
from typing import Any

from psycopg.types.json import Jsonb

from lib.document_processing.models import content_digest
from lib.search.indexing.authority_repository import fence_index, lock_checkpoint_index, lock_index
from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.errors import IndexCheckpointConflict
from lib.search.indexing.input_repository import load_input, load_manifest
from lib.search.indexing.models import IndexBinding, IndexInput, IndexManifest, VectorObservation
from lib.search.indexing.vectors import VectorCheckpoint, canonical_checkpoint


def list_missing_inputs(cur: Any, binding: IndexBinding) -> tuple[IndexInput, ...]:
    _, header = lock_index(cur, binding)
    manifest = load_manifest(cur, binding, header)
    stored = validated_checkpoints(
        cur, binding, manifest, IndexConfiguration.model_validate(header["config_json"])
    )
    fence_index(cur, binding)
    return tuple(item for item in manifest.inputs if item.id not in stored)


def persist_vector(cur: Any, binding: IndexBinding, observation: VectorObservation) -> str:
    header = lock_checkpoint_index(cur, binding)
    item = load_input(cur, binding, header, observation.input_id)
    config = IndexConfiguration.model_validate(header["config_json"])
    checkpoint = canonical_checkpoint(observation, item, config)
    cur.execute(
        "SELECT *,embedding::text AS vector_text FROM document_index_vector_checkpoints "
        "WHERE input_id=%s",
        (item.id,),
    )
    existing = cur.fetchone()
    if existing:
        if existing["content_sha256"] != checkpoint.content_sha256:
            raise IndexCheckpointConflict(
                "Candidate vector checkpoint already contains different content."
            )
        _validated_checkpoint(existing, item, config)
        fence_index(cur, binding)
        return checkpoint.content_sha256
    if header["state"] != "embedding":
        raise IndexCheckpointConflict("Sealed candidate indexes cannot acquire new vectors.")
    cur.execute(
        """INSERT INTO document_index_vector_checkpoints
        (input_id,index_generation_id,modality,dimensions,embedding,vector_sha256,observation_json,content_sha256)
        VALUES (%s,%s,%s,%s,%s::vector,%s,%s,%s)""",
        (
            item.id,
            binding.index_generation_id,
            item.modality,
            config.space(item.modality).dimensions,
            json.dumps(checkpoint.observation.values),
            checkpoint.vector_sha256,
            Jsonb(checkpoint.observation.model_dump(mode="json")),
            checkpoint.content_sha256,
        ),
    )
    fence_index(cur, binding)
    return checkpoint.content_sha256


def seal_index(cur: Any, binding: IndexBinding) -> dict[str, Any]:
    _, header = lock_index(cur, binding)
    manifest = load_manifest(cur, binding, header)
    config = IndexConfiguration.model_validate(header["config_json"])
    stored = validated_checkpoints(cur, binding, manifest, config)
    if set(stored) != {item.id for item in manifest.inputs}:
        raise IndexCheckpointConflict(
            "Candidate index cannot seal with missing vector checkpoints."
        )
    completion = {
        "schema_version": "structura.native_index_completion.v1",
        "index_generation_id": str(binding.index_generation_id),
        "manifest_sha256": manifest.fingerprint,
        "input_count": len(manifest.inputs),
        "page_count": len(manifest.pages),
        "vectors": [
            {
                "input_id": str(item.id),
                "content_sha256": stored[item.id].content_sha256,
                "vector_sha256": stored[item.id].vector_sha256,
            }
            for item in manifest.inputs
        ],
        "modalities": [
            {
                "modality": modality,
                "eligible": sum(item.modality == modality for item in manifest.inputs),
                "completed": sum(item.modality == modality for item in manifest.inputs),
            }
            for modality in config.modalities
        ],
        "fact_basis": "not_collected",
        "metadata_basis": "not_collected",
        "retrieval_quality": "not_evaluated",
        "live_invocation_attestation": "not_evaluated",
    }
    digest = content_digest(completion)
    if header["completion_json"] is not None:
        if header["completion_json"] != completion or header["completion_sha256"] != digest:
            raise IndexCheckpointConflict("Candidate completion content is inconsistent.")
    else:
        cur.execute(
            "UPDATE document_index_generations SET "
            "state='sealed',completion_json=%s,completion_sha256=%s,"
            "sealed_at=clock_timestamp() WHERE id=%s AND state='embedding'",
            (Jsonb(completion), digest, binding.index_generation_id),
        )
    fence_index(cur, binding)
    return completion


def validated_checkpoints(
    cur: Any,
    binding: IndexBinding,
    manifest: IndexManifest,
    config: IndexConfiguration,
) -> dict[Any, VectorCheckpoint]:
    cur.execute(
        "SELECT *,embedding::text AS vector_text FROM document_index_vector_checkpoints "
        "WHERE index_generation_id=%s",
        (binding.index_generation_id,),
    )
    expected = {item.id: item for item in manifest.inputs}
    checkpoints = {}
    for row in cur.fetchall():
        item = expected.get(row["input_id"])
        if item is None:
            raise IndexCheckpointConflict("Stored vector is outside the frozen input set.")
        checkpoints[item.id] = _validated_checkpoint(row, item, config)
    return checkpoints


def _validated_checkpoint(
    row: dict[str, Any], item: IndexInput, config: IndexConfiguration
) -> VectorCheckpoint:
    observation = VectorObservation.model_validate(row["observation_json"])
    checkpoint = canonical_checkpoint(observation, item, config)
    persisted = canonical_checkpoint(
        observation.model_copy(update={"values": tuple(json.loads(row["vector_text"]))}),
        item,
        config,
    )
    if (
        row["modality"] != item.modality
        or row["dimensions"] != config.space(item.modality).dimensions
        or checkpoint.content_sha256 != row["content_sha256"]
        or checkpoint.vector_sha256 != row["vector_sha256"]
        or persisted.vector_sha256 != checkpoint.vector_sha256
    ):
        raise IndexCheckpointConflict(
            "Stored vector bytes or identity do not match their checkpoint."
        )
    return checkpoint
