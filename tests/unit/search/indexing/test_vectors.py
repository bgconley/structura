from __future__ import annotations

import math
import struct
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.models import VectorObservation
from lib.search.indexing.vectors import canonical_checkpoint
from tests.unit.search.indexing.conftest import observation


def test_float32_roundtrip_is_idempotent_and_does_not_silently_round_identity(candidate):
    config, manifest = candidate
    original = observation(manifest.inputs[0], config)
    checkpoint = canonical_checkpoint(original, manifest.inputs[0], config)
    assert checkpoint.observation.values[0] == struct.unpack("!f", struct.pack("!f", 0.1))[0]
    assert checkpoint.observation.values[0] != original.values[0]
    assert canonical_checkpoint(checkpoint.observation, manifest.inputs[0], config) == checkpoint
    changed = original.model_copy(update={"invocation_id": uuid4()})
    assert (
        canonical_checkpoint(changed, manifest.inputs[0], config).content_sha256
        != checkpoint.content_sha256
    )


@pytest.mark.parametrize("values", [(True,), ("1",), (math.nan,), (math.inf,)])
def test_invalid_numeric_coercions_are_rejected(candidate, values):
    config, manifest = candidate
    payload = observation(manifest.inputs[0], config).model_dump(mode="json")
    payload["values"] = values
    with pytest.raises(ValidationError):
        VectorObservation.model_validate(payload)


@pytest.mark.parametrize("values", [(0.0,) * 1536, (1e-46,) * 1536, (1e39,) * 1536, (1.0,) * 2048])
def test_wrong_dimension_zero_underflow_and_overflow_fail(candidate, values):
    config, manifest = candidate
    value = observation(manifest.inputs[0], config).model_copy(update={"values": values})
    with pytest.raises(IndexCandidateError):
        canonical_checkpoint(value, manifest.inputs[0], config)


@pytest.mark.parametrize(
    "update",
    [
        {"input_id": uuid4()},
        {"model_input_sha256": "f" * 64},
        {"profile": "other:v2"},
        {"reported_model": "other"},
        {"declared_artifact_revision": "other"},
        {"model_mode": "live"},
    ],
)
def test_observation_cannot_switch_input_profile_artifact_or_mode(candidate, update):
    config, manifest = candidate
    value = observation(manifest.inputs[0], config).model_copy(update=update)
    with pytest.raises(IndexCandidateError, match="frozen"):
        canonical_checkpoint(value, manifest.inputs[0], config)


def test_signed_zero_has_one_durable_vector_encoding(candidate):
    config, manifest = candidate
    value = observation(manifest.inputs[0], config).model_copy(
        update={"values": (1.0, -0.0) + (0.0,) * 1534}
    )
    normalized = canonical_checkpoint(value, manifest.inputs[0], config)
    assert math.copysign(1, normalized.observation.values[1]) == 1
