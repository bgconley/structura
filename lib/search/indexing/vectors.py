"""Canonical float32 vector persistence, separate from reported model provenance."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from lib.document_processing.models import content_digest
from lib.model_runtime.clients.embedding_response import validated_vector
from lib.model_runtime.http_client import ModelProtocolError
from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.models import IndexInput, VectorObservation


@dataclass(frozen=True)
class VectorCheckpoint:
    observation: VectorObservation
    vector_sha256: str
    content_sha256: str


def canonical_checkpoint(
    observation: VectorObservation,
    item: IndexInput,
    configuration: IndexConfiguration,
) -> VectorCheckpoint:
    space = configuration.space(item.modality)
    if (
        observation.input_id != item.id
        or observation.model_input_sha256 != item.model_input_sha256
        or observation.profile != space.profile
        or observation.reported_model != space.served_model
        or observation.declared_artifact_revision != space.protocol.artifact_revision
        or observation.identity_source != space.protocol.identity_policy
        or observation.model_mode != configuration.model_mode
    ):
        raise IndexCandidateError(
            "Vector observation does not match its frozen input and model space."
        )
    try:
        vector = tuple(
            0.0 if v == 0 else v
            for v in validated_vector(observation.values, dimensions=space.dimensions)
        )
        encoded = struct.pack(f"!{space.dimensions}f", *vector)
        values = tuple(struct.unpack(f"!{space.dimensions}f", encoded))
        validated_vector(values, dimensions=space.dimensions)
    except (ModelProtocolError, OverflowError, struct.error):
        raise IndexCandidateError("Vector does not fit its finite nonzero float32 space.") from None
    normalized = observation.model_copy(update={"values": values})
    vector_hash = hashlib.sha256(b"structura-float32be-v1\0" + encoded).hexdigest()
    return VectorCheckpoint(
        normalized,
        vector_hash,
        content_digest(
            {"observation": normalized.model_dump(mode="json"), "vector_sha256": vector_hash}
        ),
    )
