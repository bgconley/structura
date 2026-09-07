"""Fingerprint the complete input and declared embedding-space semantics."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Literal

from lib.model_runtime.contracts import EmbeddingRequest
from lib.model_runtime.embedding_protocol import VISUAL_SYSTEM_INSTRUCTION
from lib.model_runtime.profiles import ModelProfile


def embedding_input_hashes(request: EmbeddingRequest, profile: ModelProfile) -> tuple[str, ...]:
    if profile.embedding_protocol is None:
        raise ValueError("Embedding profile must declare its protocol.")
    return tuple(
        embedding_input_identity(
            item.sha256, profile, dimensions=request.output_dimensions, purpose=request.purpose
        )
        for item in request.inputs
    )


def embedding_input_identity(
    content_sha256: str,
    profile: ModelProfile,
    *,
    dimensions: int,
    purpose: Literal["document", "query"],
) -> str:
    """Bind a previously verified content digest to the complete model space.

    This does not attest bytes or invocation. Callers using persisted descriptors
    must verify the actual input bytes separately before sending them to a model.
    """
    if not isinstance(content_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", content_sha256):
        raise ValueError("Embedding content identity must be a SHA256 digest.")
    if profile.embedding_protocol is None:
        raise ValueError("Embedding profile must declare its protocol.")
    identity = {
        "profile": profile.name,
        "base_model": profile.base_model,
        "served_model": profile.served_model_name or profile.base_model,
        "protocol": asdict(profile.embedding_protocol),
        "dimensions": dimensions,
        "purpose": purpose,
        "visual_system_instruction": (
            VISUAL_SYSTEM_INSTRUCTION if profile.engine == "visual_embedding" else None
        ),
    }
    return hashlib.sha256(
        json.dumps(
            {**identity, "input_sha256": content_sha256},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
