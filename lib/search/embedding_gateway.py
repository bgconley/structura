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


@dataclass(frozen=True)
class VisualEmbeddingInput:
    descriptor_text: str
    image_bytes: bytes
    mime_type: str
    content_sha256: str


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


class DeterministicVisualEmbeddingGateway(DeterministicEmbeddingGateway):
    """Deterministic local visual adapter that uses protected image bytes plus page context."""

    def embed_assets(self, assets: list[VisualEmbeddingInput]) -> list[EmbeddedText]:
        return [
            EmbeddedText(
                text=asset.descriptor_text,
                values=_visual_hash_embedding(asset, self.profile),
                profile=self.profile,
            )
            for asset in assets
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
        name="structura-local-visual-byte-embedding",
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
    return _tokens_hash_embedding(_expanded_tokens(text), profile)


def _visual_hash_embedding(asset: VisualEmbeddingInput, profile: EmbeddingProfile) -> list[float]:
    actual_hash = hashlib.sha256(asset.image_bytes).hexdigest()
    if actual_hash != asset.content_sha256.lower():
        raise EmbeddingGatewayError("Visual asset bytes do not match the expected SHA-256 digest.")
    byte_tokens = [
        f"visual-bytes:{actual_hash[index : index + 8]}" for index in range(0, len(actual_hash), 8)
    ]
    byte_tokens.extend(
        f"byte-bucket:{bucket}:{count}"
        for bucket, count in enumerate(_byte_histogram(asset.image_bytes, buckets=16))
        if count
    )
    tokens = [
        *_expanded_tokens(asset.descriptor_text),
        f"mime:{asset.mime_type.casefold()}",
        f"size:{len(asset.image_bytes)}",
        *byte_tokens,
    ]
    return _tokens_hash_embedding(tokens, profile)


def _tokens_hash_embedding(tokens: list[str], profile: EmbeddingProfile) -> list[float]:
    vector = [0.0] * profile.dimensions
    for token in tokens:
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


def _byte_histogram(data: bytes, *, buckets: int) -> list[int]:
    histogram = [0] * buckets
    for byte in data:
        histogram[byte * buckets // 256] += 1
    return histogram


def _expanded_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        expanded.extend(EMBEDDING_SYNONYMS.get(token, ()))
    return expanded
