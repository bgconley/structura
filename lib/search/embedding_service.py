from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.search.embedding_gateway import (
    DeterministicEmbeddingGateway,
    EmbeddingProfile,
    default_text_embedding_profile,
    default_visual_embedding_profile,
)
from lib.search.embedding_repository import (
    count_visual_eligible_pages_without_assets,
    list_text_embedding_sources,
    list_visual_embedding_sources,
    persist_embedding,
    persist_text_embedding,
    refresh_search_projection,
)


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
        gateway: DeterministicEmbeddingGateway | None = None,
        visual_profile: EmbeddingProfile | None = None,
        visual_gateway: DeterministicEmbeddingGateway | None = None,
    ) -> None:
        settings = get_settings()
        self.profile = profile or default_text_embedding_profile(settings.embedding_text_dimensions)
        self.gateway = gateway or DeterministicEmbeddingGateway(self.profile)
        self.visual_profile = visual_profile or default_visual_embedding_profile(
            settings.embedding_visual_dimensions
        )
        self.visual_gateway = visual_gateway or DeterministicEmbeddingGateway(self.visual_profile)
        self.visual_enabled = settings.embedding_visual_enabled

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
        embedded = self.visual_gateway.embed_texts([source.text for source in sources])
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
