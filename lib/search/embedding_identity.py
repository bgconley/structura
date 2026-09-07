"""Versioned input identity carried with vectors into index persistence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from lib.search.embedding_gateway import EmbeddingProfile


@dataclass(frozen=True)
class EmbeddingInputIdentity:
    sha256: str
    scheme: Literal["model-input-v1", "fixture-input-v1"]
    purpose: Literal["document", "query"] = "document"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("Embedding input identity requires a SHA-256 digest.")
        if self.scheme not in {"model-input-v1", "fixture-input-v1"}:
            raise ValueError("Embedding input identity scheme is unsupported.")
        if self.purpose not in {"document", "query"}:
            raise ValueError("Embedding input identity purpose is unsupported.")

    def metadata(self) -> dict[str, str]:
        return {"sha256": self.sha256, "scheme": self.scheme, "purpose": self.purpose}


def fixture_input_identity(
    text: str,
    profile: EmbeddingProfile,
    *,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
    purpose: Literal["document", "query"] = "document",
) -> EmbeddingInputIdentity:
    # Fixture spaces retain their original profile/vector algorithm. Their
    # fingerprint is explicitly separate from any live model/protocol identity.
    content = {
        "kind": "deterministic_fixture",
        "profile": asdict(profile),
        "purpose": purpose,
        "text": text,
        "image_sha256": hashlib.sha256(image_bytes).hexdigest()
        if image_bytes is not None
        else None,
        "mime_type": mime_type,
    }
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return EmbeddingInputIdentity(digest, "fixture-input-v1", purpose)
