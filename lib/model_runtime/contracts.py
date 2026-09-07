from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal


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
class TextGenerateRequest:
    """Text-only structured generation (no image inputs).

    Used by the extractive text lane for enum-constrained selection calls
    (column-role labeling, span selection); the schema is mandatory and the
    response must validate against it, mirroring the vision contract.
    """

    profile_name: str
    prompt_version: str
    prompt: str
    response_schema_name: str | None
    max_output_tokens: int
    temperature: float
    timeout_seconds: int
    response_json_schema: dict[str, Any] | None = None
    seed: int | None = 0


@dataclass(frozen=True)
class TextGenerateResponse:
    profile_name: str
    model_name: str
    model_version: str
    source_engine: str
    prompt_version: str
    raw_text: str
    normalized_json: dict[str, object]
    prompt_sha256: str
    latency_ms: int
    finish_reason: str | None = None
    usage_json: dict[str, object] = field(default_factory=dict)
    structured_output_used: bool = False


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


@dataclass(frozen=True)
class EmbeddingInput:
    text: str
    image_bytes: bytes | None = None
    mime_type: str | None = None

    @property
    def sha256(self) -> str:
        content = {
            "text": self.text,
            "mime_type": self.mime_type,
            "image_sha256": (
                hashlib.sha256(self.image_bytes).hexdigest()
                if self.image_bytes is not None
                else None
            ),
        }
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class EmbeddingRequest:
    profile_name: str
    inputs: tuple[EmbeddingInput, ...]
    output_dimensions: int
    timeout_seconds: int
    purpose: Literal["document", "query"] = "document"


@dataclass(frozen=True)
class EmbeddingResponse:
    profile_name: str
    model_name: str
    model_version: str
    dimensions: int
    vectors: tuple[tuple[float, ...], ...]
    input_sha256: tuple[str, ...]
    latency_ms: int
    identity_source: Literal["reported_model", "deployment_pinned"] = "reported_model"
    artifact_revision: str | None = None
