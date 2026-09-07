from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace

import pytest

from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest
from lib.model_runtime.embedding_identity import embedding_input_hashes, embedding_input_identity
from lib.model_runtime.embedding_protocol import VISUAL_SYSTEM_INSTRUCTION
from lib.model_runtime.profiles import (
    TEXT_EMBED_BLACKBIRD_PROFILE,
    VISUAL_EMBED_BLACKBIRD_PROFILE,
    get_model_profile,
)


@pytest.mark.parametrize("name", [TEXT_EMBED_BLACKBIRD_PROFILE, VISUAL_EMBED_BLACKBIRD_PROFILE])
@pytest.mark.parametrize("purpose", ["document", "query"])
def test_shared_precomputed_identity_is_byte_for_byte_legacy_hash(name, purpose):
    profile = get_model_profile(name)
    item = EmbeddingInput(
        text="Référence 10.00",
        image_bytes=b"source pixels" if profile.engine == "visual_embedding" else None,
        mime_type="image/png" if profile.engine == "visual_embedding" else None,
    )
    request = EmbeddingRequest(
        profile_name=name,
        inputs=(item,),
        output_dimensions=profile.output_dimensions,
        timeout_seconds=10,
        purpose=purpose,
    )
    legacy = {
        "profile": profile.name,
        "base_model": profile.base_model,
        "served_model": profile.served_model_name or profile.base_model,
        "protocol": asdict(profile.embedding_protocol),
        "dimensions": request.output_dimensions,
        "purpose": purpose,
        "visual_system_instruction": VISUAL_SYSTEM_INSTRUCTION
        if profile.engine == "visual_embedding"
        else None,
        "input_sha256": item.sha256,
    }
    expected = hashlib.sha256(
        json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert embedding_input_hashes(request, profile) == (expected,)
    assert (
        embedding_input_identity(
            item.sha256, profile, dimensions=request.output_dimensions, purpose=purpose
        )
        == expected
    )
    assert (
        embedding_input_identity(item.sha256, profile, dimensions=1024, purpose=purpose) != expected
    )
    changed = replace(
        profile,
        embedding_protocol=replace(profile.embedding_protocol, artifact_revision="different"),
    )
    assert (
        embedding_input_identity(
            item.sha256, changed, dimensions=request.output_dimensions, purpose=purpose
        )
        != expected
    )


@pytest.mark.parametrize("digest", ["", "F" * 64, "a" * 63, "g" * 64, "a" * 64 + "\n"])
def test_precomputed_identity_refuses_noncanonical_hash(digest):
    with pytest.raises(ValueError, match="SHA256"):
        embedding_input_identity(
            digest,
            get_model_profile(TEXT_EMBED_BLACKBIRD_PROFILE),
            dimensions=1536,
            purpose="document",
        )


def test_empty_request_still_rejects_undeclared_profile():
    profile = replace(get_model_profile(TEXT_EMBED_BLACKBIRD_PROFILE), embedding_protocol=None)
    request = EmbeddingRequest(
        profile_name=profile.name, inputs=(), output_dimensions=1536, timeout_seconds=10
    )
    with pytest.raises(ValueError, match="protocol"):
        embedding_input_hashes(request, profile)
