from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.search.embedding_gateway import (
    DeterministicEmbeddingGateway,
    EmbeddingProfile,
    default_text_embedding_profile,
)
from lib.search.embedding_repository import (
    list_text_embedding_sources,
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


class EmbeddingService:
    def __init__(
        self,
        *,
        profile: EmbeddingProfile | None = None,
        gateway: DeterministicEmbeddingGateway | None = None,
    ) -> None:
        settings = get_settings()
        self.profile = profile or default_text_embedding_profile(settings.embedding_text_dimensions)
        self.gateway = gateway or DeterministicEmbeddingGateway(self.profile)

    def embed_document(
        self,
        document_id: UUID,
        *,
        force_reembed: bool = False,
    ) -> EmbeddingRunSummary:
        with db_connection() as conn:
            with conn.cursor() as cur:
                refresh_search_projection(cur, document_id)
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
            conn.commit()
        return EmbeddingRunSummary(
            document_id=document_id,
            source_count=len(sources),
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            model_name=self.profile.name,
            model_version=self.profile.version,
            dimensions=self.profile.dimensions,
        )
