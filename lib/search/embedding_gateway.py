from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Literal

EMBEDDING_SYNONYMS = {
    "owe": ("due", "responsibility", "balance", "amount"),
    "owed": ("due", "responsibility", "balance", "amount"),
    "money": ("amount", "total", "payment", "paid"),
    "claim": ("claim", "eob", "insurance"),
    "medical": ("medical", "eob", "insurance", "patient"),
    "warranty": ("coverage", "replacement", "repair"),
    "receipt": ("merchant", "purchase", "transaction", "total"),
    "invoice": ("bill", "vendor", "due", "total"),
}


@dataclass(frozen=True)
class EmbeddingProfile:
    name: str
    version: str
    modality: Literal["text", "visual", "mixed"]
    dimensions: int
    metric: Literal["cosine", "l2", "inner_product"]


@dataclass(frozen=True)
class EmbeddedText:
    text: str
    values: list[float]
    profile: EmbeddingProfile


class EmbeddingGatewayError(Exception):
    pass


class DeterministicEmbeddingGateway:
    """Local fixture embedding adapter that requires no external model service."""

    def __init__(self, profile: EmbeddingProfile) -> None:
        if profile.dimensions <= 0:
            raise EmbeddingGatewayError("Embedding dimensions must be positive.")
        self.profile = profile

    def embed_texts(self, texts: list[str]) -> list[EmbeddedText]:
        return [
            EmbeddedText(
                text=text,
                values=_token_hash_embedding(text, self.profile),
                profile=self.profile,
            )
            for text in texts
        ]


def default_text_embedding_profile(dimensions: int = 1536) -> EmbeddingProfile:
    return EmbeddingProfile(
        name="structura-fixture-text-embedding",
        version="v1",
        modality="text",
        dimensions=dimensions,
        metric="cosine",
    )


def default_visual_embedding_profile(dimensions: int = 1024) -> EmbeddingProfile:
    return EmbeddingProfile(
        name="structura-fixture-visual-embedding",
        version="v1",
        modality="visual",
        dimensions=dimensions,
        metric="cosine",
    )


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token_hash_embedding(text: str, profile: EmbeddingProfile) -> list[float]:
    vector = [0.0] * profile.dimensions
    for token in _expanded_tokens(text):
        digest = hashlib.blake2b(
            f"{profile.name}:{profile.version}:{token}".encode(),
            digest_size=16,
        ).digest()
        bucket = int.from_bytes(digest[:8], "big") % profile.dimensions
        sign = 1.0 if digest[8] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _expanded_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        expanded.extend(EMBEDDING_SYNONYMS.get(token, ()))
    return expanded
