from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


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
    response_json_schema: dict[str, Any] | None = None
    allow_structured_output_fallback: bool = True
    structured_output_mode: str = "response_format_json_schema"
    seed: int | None = 0


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
    finish_reason: str | None = None
    usage_json: dict[str, object] = field(default_factory=dict)
    structured_output_used: bool = False
    structured_output_fallback_reason: str | None = None


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
