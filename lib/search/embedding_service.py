from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.model_runtime.clients.text_embeddings import TextEmbeddingClient
from lib.model_runtime.clients.visual_embeddings import VisualEmbeddingClient
from lib.model_runtime.profiles import get_model_profile
from lib.search.embedding_gateway import (
    DeterministicEmbeddingGateway,
    DeterministicVisualEmbeddingGateway,
    EmbeddingProfile,
    VisualEmbeddingInput,
    default_text_embedding_profile,
    default_visual_embedding_profile,
)
from lib.search.embedding_repository import (
    EmbeddingSource,
    count_visual_eligible_pages_without_assets,
    list_text_embedding_sources,
    list_visual_embedding_sources,
    persist_embedding,
    persist_text_embedding,
    refresh_search_projection,
)
from lib.search.embeddings.text_model import TextModelEmbeddingGateway
from lib.search.embeddings.visual_model import VisualModelEmbeddingGateway
from lib.storage import ObjectStorage


class TextEmbeddingGatewayProtocol(Protocol):
    profile: EmbeddingProfile

    def embed_texts(self, texts: list[str]) -> list[Any]: ...


class VisualEmbeddingGatewayProtocol(Protocol):
    profile: EmbeddingProfile

    def embed_assets(self, assets: list[VisualEmbeddingInput]) -> list[Any]: ...


@dataclass(frozen=True)
class EmbeddingRunSummary:
    document_id: UUID
    source_count: int
    inserted_count: int
    skipped_count: int
    model_name: str
    model_version: str
    dimensions: int
    modality_counts: dict[str, int]


class EmbeddingService:
    def __init__(
        self,
        *,
        profile: EmbeddingProfile | None = None,
        gateway: TextEmbeddingGatewayProtocol | None = None,
        visual_profile: EmbeddingProfile | None = None,
        visual_gateway: VisualEmbeddingGatewayProtocol | None = None,
        storage: ObjectStorage | None = None,
    ) -> None:
        settings = get_settings()
        self.gateway = gateway or _default_text_gateway(
            settings=settings,
            profile=profile,
        )
        self.profile = self.gateway.profile
        self.visual_gateway = visual_gateway or _default_visual_gateway(
            settings=settings,
            profile=visual_profile,
        )
        self.visual_profile = self.visual_gateway.profile
        self.visual_enabled = settings.embedding_visual_enabled
        self.storage = storage or ObjectStorage(settings=settings)

    def embed_document(
        self,
        document_id: UUID,
        *,
        force_reembed: bool = False,
        modalities: tuple[str, ...] = ("text",),
    ) -> EmbeddingRunSummary:
        requested = tuple(dict.fromkeys(modalities or ("text",)))
        with db_connection() as conn:
            with conn.cursor() as cur:
                refresh_search_projection(cur, document_id)
                inserted_count = 0
                skipped_count = 0
                modality_counts: dict[str, int] = {}
                if "text" in requested or "mixed" in requested:
                    text_inserted, text_skipped, text_count = self._persist_text_embeddings(
                        cur,
                        document_id,
                        force_reembed=force_reembed,
                    )
                    inserted_count += text_inserted
                    skipped_count += text_skipped
                    modality_counts["text"] = text_count
                if "visual" in requested or "mixed" in requested:
                    visual_inserted, visual_skipped, visual_count = self._persist_visual_embeddings(
                        cur,
                        document_id,
                        force_reembed=force_reembed,
                    )
                    inserted_count += visual_inserted
                    skipped_count += visual_skipped
                    modality_counts["visual"] = visual_count
            conn.commit()
        summary_profile = self._summary_profile(requested)
        return EmbeddingRunSummary(
            document_id=document_id,
            source_count=sum(modality_counts.values()),
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            model_name=summary_profile.name,
            model_version=summary_profile.version,
            dimensions=summary_profile.dimensions,
            modality_counts=modality_counts,
        )

    def _summary_profile(self, requested: tuple[str, ...]) -> EmbeddingProfile:
        if requested == ("visual",):
            return self.visual_profile
        return self.profile

    def _persist_text_embeddings(
        self,
        cur: Any,
        document_id: UUID,
        *,
        force_reembed: bool,
    ) -> tuple[int, int, int]:
        sources = list_text_embedding_sources(cur, document_id)
        embedded = self.gateway.embed_texts([source.text for source in sources])
        inserted_count = 0
        skipped_count = 0
        for source, embedding in zip(sources, embedded, strict=True):
            if persist_text_embedding(
                cur,
                source=source,
                embedding=embedding,
                force_reembed=force_reembed,
            ):
                inserted_count += 1
            else:
                skipped_count += 1
        return inserted_count, skipped_count, len(sources)

    def _persist_visual_embeddings(
        self,
        cur: Any,
        document_id: UUID,
        *,
        force_reembed: bool,
    ) -> tuple[int, int, int]:
        if not self.visual_enabled:
            return 0, 0, 0
        missing_assets = count_visual_eligible_pages_without_assets(cur, document_id)
        if missing_assets:
            raise ValueError("Visual embedding requested before page image assets are available.")
        sources = list_visual_embedding_sources(cur, document_id)
        embedded = self.visual_gateway.embed_assets(
            [_visual_embedding_input(self.storage, source) for source in sources]
        )
        inserted_count = 0
        skipped_count = 0
        for source, embedding in zip(sources, embedded, strict=True):
            if persist_embedding(
                cur,
                source=source,
                embedding=embedding,
                force_reembed=force_reembed,
            ):
                inserted_count += 1
            else:
                skipped_count += 1
        return inserted_count, skipped_count, len(sources)


def _visual_embedding_input(
    storage: ObjectStorage, source: EmbeddingSource
) -> VisualEmbeddingInput:
    asset_uri = source.metadata.get("assetUri")
    mime_type = source.metadata.get("assetMimeType")
    if not isinstance(asset_uri, str) or not asset_uri:
        raise ValueError("Visual embedding source is missing asset URI.")
    if not isinstance(mime_type, str) or not mime_type.startswith("image/"):
        raise ValueError("Visual embedding source must reference an image asset.")
    image_path = storage.path_for_uri(asset_uri)
    image_bytes = image_path.read_bytes()
    if not image_bytes:
        raise ValueError("Visual embedding source image asset is empty.")
    return VisualEmbeddingInput(
        descriptor_text=source.text,
        image_bytes=image_bytes,
        mime_type=mime_type,
        content_sha256=source.content_sha256,
    )


def _default_text_gateway(
    *,
    settings: Any,
    profile: EmbeddingProfile | None,
) -> TextEmbeddingGatewayProtocol:
    if settings.model_mode == "fixture":
        resolved_profile = profile or default_text_embedding_profile(
            settings.embedding_text_dimensions
        )
        return DeterministicEmbeddingGateway(resolved_profile)
    model_profile = get_model_profile(settings.text_embed_profile)
    return TextModelEmbeddingGateway(
        client=TextEmbeddingClient(
            profile=model_profile,
            http_client_base_url=settings.model_text_embed_url,
        ),
        profile_name=model_profile.name,
    )


def _default_visual_gateway(
    *,
    settings: Any,
    profile: EmbeddingProfile | None,
) -> VisualEmbeddingGatewayProtocol:
    if settings.model_mode == "fixture":
        resolved_profile = profile or default_visual_embedding_profile(
            settings.embedding_visual_dimensions
        )
        return DeterministicVisualEmbeddingGateway(resolved_profile)
    model_profile = get_model_profile(settings.visual_embed_profile)
    return VisualModelEmbeddingGateway(
        client=VisualEmbeddingClient(
            profile=model_profile,
            http_client_base_url=settings.model_visual_embed_url,
        ),
        profile_name=model_profile.name,
    )
