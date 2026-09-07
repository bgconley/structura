"""Fingerprint the complete input and declared embedding-space semantics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from lib.model_runtime.contracts import EmbeddingRequest
from lib.model_runtime.embedding_protocol import VISUAL_SYSTEM_INSTRUCTION
from lib.model_runtime.profiles import ModelProfile


def embedding_input_hashes(request: EmbeddingRequest, profile: ModelProfile) -> tuple[str, ...]:
    if profile.embedding_protocol is None:
        raise ValueError("Embedding profile must declare its protocol.")
    identity = {
        "profile": profile.name,
        "base_model": profile.base_model,
        "served_model": profile.served_model_name or profile.base_model,
        "protocol": asdict(profile.embedding_protocol),
        "dimensions": request.output_dimensions,
        "purpose": request.purpose,
        "visual_system_instruction": (
            VISUAL_SYSTEM_INSTRUCTION if profile.engine == "visual_embedding" else None
        ),
    }
    return tuple(
        hashlib.sha256(
            json.dumps(
                {**identity, "input_sha256": item.sha256},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        for item in request.inputs
    )
