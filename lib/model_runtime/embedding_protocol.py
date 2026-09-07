"""Declared wire format and identity policy for an embedding deployment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

VISUAL_SYSTEM_INSTRUCTION = "Represent the user's input."


@dataclass(frozen=True)
class EmbeddingProtocol:
    api_flavor: Literal["tei", "openai"]
    dimensions_policy: Literal["requested", "native"]
    input_format: Literal["raw_text", "qwen_text", "qwen_vl_messages"]
    identity_policy: Literal["reported_model", "deployment_pinned"]
    artifact_revision: str | None = None
    query_instruction: str | None = None

    def __post_init__(self) -> None:
        if self.api_flavor not in {"tei", "openai"}:
            raise ValueError("Embedding protocol must declare a supported API flavor.")
        if self.dimensions_policy not in {"requested", "native"}:
            raise ValueError("Embedding protocol must declare a dimensions policy.")
        if self.input_format not in {"raw_text", "qwen_text", "qwen_vl_messages"}:
            raise ValueError("Embedding protocol must declare a supported input format.")
        if self.identity_policy not in {"reported_model", "deployment_pinned"}:
            raise ValueError("Embedding protocol must declare an identity policy.")
        if self.api_flavor == "tei" and (
            self.identity_policy != "deployment_pinned" or self.input_format != "raw_text"
        ):
            raise ValueError("TEI requires raw text and explicit deployment-pinned identity.")
        if self.api_flavor != "tei" and self.identity_policy == "deployment_pinned":
            raise ValueError("OpenAI embedding responses must report their model identity.")
        if self.input_format == "qwen_text" and not self.query_instruction:
            raise ValueError("Qwen text embeddings require a query instruction.")

    @property
    def endpoint(self) -> str:
        return "/embed" if self.api_flavor == "tei" else "/v1/embeddings"
