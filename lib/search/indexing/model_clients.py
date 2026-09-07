"""Explicit native-index clients preserving the full embedding response contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from lib.config import Settings
from lib.model_runtime.clients.text_embeddings import TextEmbeddingClient
from lib.model_runtime.clients.visual_embeddings import VisualEmbeddingClient
from lib.model_runtime.contracts import EmbeddingRequest, EmbeddingResponse
from lib.model_runtime.credentials import model_api_key
from lib.model_runtime.profiles import ModelProfile, get_model_profile
from lib.search.indexing.configuration import IndexConfiguration, Modality
from lib.search.indexing.errors import IndexCandidateError


class CandidateEmbeddingClient(Protocol):
    profile: ModelProfile

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...


@dataclass(frozen=True)
class CandidateEmbeddingClients:
    configuration_sha256: str
    model_mode: Literal["live", "fixture"]
    text: CandidateEmbeddingClient | None
    visual: CandidateEmbeddingClient | None

    def for_modality(self, modality: Modality) -> CandidateEmbeddingClient:
        client = self.text if modality == "text" else self.visual
        if client is None:
            raise IndexCandidateError("Requested candidate modality has no explicit model client.")
        return client

    def validate(self, configuration: IndexConfiguration) -> None:
        if (self.configuration_sha256, self.model_mode) != (
            configuration.fingerprint,
            configuration.model_mode,
        ):
            raise IndexCandidateError("Candidate clients do not match the frozen configuration.")
        for modality in configuration.modalities:
            if self.for_modality(modality).profile != get_model_profile(
                configuration.space(modality).profile
            ):
                raise IndexCandidateError(
                    "Candidate client profile differs from the frozen model space."
                )


def candidate_embedding_clients(
    configuration: IndexConfiguration,
    settings: Settings,
    *,
    text_transport: httpx.BaseTransport | None = None,
    visual_transport: httpx.BaseTransport | None = None,
) -> CandidateEmbeddingClients:
    """Use accepted frozen profiles and explicit configured endpoints/credentials.

    Settings never select/substitute an embedding profile here. Fixture clients
    must be supplied explicitly by tests with a fixture configuration; no fallback
    is installed if a live endpoint fails. Transports allow independent dispatch
    observation in the isolated probe without discarding response provenance.
    """
    configuration = IndexConfiguration.model_validate(configuration.model_dump(mode="json"))
    if configuration.model_mode != "live" or settings.model_mode not in {"live", "required"}:
        raise IndexCandidateError(
            "Live candidate clients require explicit live model configuration."
        )
    text = None
    visual = None
    if "text" in configuration.modalities:
        text = TextEmbeddingClient(
            profile=get_model_profile(configuration.space("text").profile),
            http_client_base_url=settings.model_text_embed_url,
            api_key=model_api_key(
                settings.model_text_embed_api_key, settings.model_text_embed_api_key_file
            ),
            transport=text_transport,
        )
    if "visual" in configuration.modalities:
        visual = VisualEmbeddingClient(
            profile=get_model_profile(configuration.space("visual").profile),
            http_client_base_url=settings.model_visual_embed_url,
            api_key=model_api_key(
                settings.model_visual_embed_api_key, settings.model_visual_embed_api_key_file
            ),
            transport=visual_transport,
        )
    return CandidateEmbeddingClients(configuration.fingerprint, "live", text, visual)
