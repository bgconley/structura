from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.search.embedding_defaults import (
    TextEmbeddingGatewayProtocol,
    VisualAssetEmbeddingGatewayProtocol,
    default_text_embedding_gateway,
    default_visual_asset_embedding_gateway,
)
from lib.search.embedding_gateway import EmbeddingProfile, VisualEmbeddingInput
from lib.search.embedding_repository import (
    EmbeddingSource,
    count_visual_eligible_pages_without_assets,
    list_text_embedding_sources,
    list_visual_embedding_sources,
    persist_embedding,
    persist_text_embedding,
    refresh_search_projection,
)
from lib.storage import ObjectStorage


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
        visual_gateway: VisualAssetEmbeddingGatewayProtocol | None = None,
        storage: ObjectStorage | None = None,
    ) -> None:
        settings = get_settings()
        self.gateway = gateway or default_text_embedding_gateway(
            settings=settings,
            profile=profile,
        )
        self.profile = self.gateway.profile
        self.visual_gateway = visual_gateway or default_visual_asset_embedding_gateway(
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
                source=_with_embedding_provenance(source, self.profile),
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
                source=_with_embedding_provenance(source, self.visual_profile),
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


def _with_embedding_provenance(
    source: EmbeddingSource,
    profile: EmbeddingProfile,
) -> EmbeddingSource:
    metadata = {
        **source.metadata,
        "embeddingAdapter": _embedding_adapter_name(profile),
        "embeddingModelVersion": profile.version,
        "embeddingModality": profile.modality,
    }
    return EmbeddingSource(
        owner_type=source.owner_type,
        owner_id=source.owner_id,
        document_id=source.document_id,
        text=source.text,
        metadata=metadata,
        content_sha256_override=source.content_sha256_override,
    )


def _embedding_adapter_name(profile: EmbeddingProfile) -> str:
    if profile.name == "structura-fixture-text-embedding":
        return "deterministic_text_fixture"
    if profile.name == "structura-fixture-visual-byte-embedding":
        return "deterministic_visual_byte_embedding"
    return profile.name
