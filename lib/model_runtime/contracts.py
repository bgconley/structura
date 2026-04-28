from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelImageInput:
    content: bytes
    mime_type: str
    sha256: str

    def validated_sha256(self) -> str:
        actual = hashlib.sha256(self.content).hexdigest()
        if self.sha256 and self.sha256.lower() != actual:
            raise ValueError("Model image input hash does not match content.")
        return actual


@dataclass(frozen=True)
class VisionGenerateRequest:
    profile_name: str
    prompt_version: str
    prompt: str
    image_inputs: tuple[ModelImageInput, ...]
    response_schema_name: str | None
    max_output_tokens: int
    temperature: float
    timeout_seconds: int


@dataclass(frozen=True)
class VisionGenerateResponse:
    profile_name: str
    model_name: str
    model_version: str
    source_engine: str
    prompt_version: str
    raw_text: str
    normalized_json: dict[str, object]
    confidence_json: dict[str, object]
    input_sha256: tuple[str, ...]
    latency_ms: int


@dataclass(frozen=True)
class EmbeddingInput:
    text: str
    image_bytes: bytes | None = None
    mime_type: str | None = None

    @property
    def sha256(self) -> str:
        content = self.image_bytes if self.image_bytes is not None else self.text.encode()
        return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class EmbeddingRequest:
    profile_name: str
    inputs: tuple[EmbeddingInput, ...]
    output_dimensions: int
    timeout_seconds: int


@dataclass(frozen=True)
class EmbeddingResponse:
    profile_name: str
    model_name: str
    model_version: str
    dimensions: int
    vectors: tuple[tuple[float, ...], ...]
    input_sha256: tuple[str, ...]
    latency_ms: int
