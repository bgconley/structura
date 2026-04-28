from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.search.embedding_gateway import (
    EmbeddedText,
    EmbeddingProfile,
    content_hash,
    vector_literal,
)


@dataclass(frozen=True)
class EmbeddingSource:
    owner_type: str
    owner_id: UUID
    document_id: UUID
    text: str
    metadata: dict[str, object]
    content_sha256_override: str | None = None

    @property
    def content_sha256(self) -> str:
        if self.content_sha256_override:
            return self.content_sha256_override.lower()
        return content_hash(self.text)


def refresh_search_projection(cur: Any, document_id: UUID) -> None:
    cur.execute("SELECT refresh_document_chunk_projection(%s)", (document_id,))


def list_text_embedding_sources(cur: Any, document_id: UUID) -> list[EmbeddingSource]:
    cur.execute(
        """
        SELECT
          c.id,
          c.document_id,
          c.chunk_index,
          c.page_start,
          c.page_end,
          COALESCE(NULLIF(c.bm25_text, ''), c.text_content, c.markdown_content, '') AS text
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.document_id = %s
          AND d.deleted_at IS NULL
        ORDER BY c.chunk_index
        """,
        (document_id,),
    )
    return [
        EmbeddingSource(
            owner_type="chunk",
            owner_id=cast(UUID, row["id"]),
            document_id=cast(UUID, row["document_id"]),
            text=str(row["text"] or ""),
            metadata={
                "chunkIndex": row["chunk_index"],
                "pageStart": row["page_start"],
                "pageEnd": row["page_end"],
            },
        )
        for row in cur.fetchall()
        if str(row.get("text") or "").strip()
    ]


def list_visual_embedding_sources(cur: Any, document_id: UUID) -> list[EmbeddingSource]:
    cur.execute(
        """
        SELECT
          p.id,
          p.document_id,
          p.page_number,
          p.image_asset_id,
          p.metadata_json -> 'phase8' -> 'quality' AS quality_json,
          d.title,
          d.original_filename,
          d.document_family::text AS document_family,
          a.sha256,
          a.byte_size,
          a.uri,
          a.mime_type
        FROM document_pages p
        JOIN documents d ON d.id = p.document_id
        JOIN document_assets a ON a.id = p.image_asset_id
        WHERE p.document_id = %s
          AND d.deleted_at IS NULL
          AND COALESCE(
            (p.metadata_json -> 'phase8' -> 'quality' ->> 'visualEmbeddingEligible')::boolean,
            false
          )
          AND a.is_current
        ORDER BY p.page_number
        """,
        (document_id,),
    )
    return [
        EmbeddingSource(
            owner_type="page",
            owner_id=cast(UUID, row["id"]),
            document_id=cast(UUID, row["document_id"]),
            text=_visual_descriptor(row),
            metadata={
                "pageNumber": row["page_number"],
                "imageAssetId": str(row["image_asset_id"]),
                "assetSha256": row["sha256"],
                "assetByteSize": row["byte_size"],
                "assetUri": row["uri"],
                "assetMimeType": row["mime_type"],
                "sourceBytesSha256": row["sha256"],
                "quality": row.get("quality_json") or {},
                "embeddingAdapter": "deterministic_visual_byte_embedding",
            },
            content_sha256_override=str(row["sha256"]),
        )
        for row in cur.fetchall()
    ]


def count_visual_eligible_pages_without_assets(cur: Any, document_id: UUID) -> int:
    cur.execute(
        """
        SELECT count(*) AS total
        FROM document_pages p
        WHERE p.document_id = %s
          AND COALESCE(
            (p.metadata_json -> 'phase8' -> 'quality' ->> 'visualEmbeddingEligible')::boolean,
            false
          )
          AND p.image_asset_id IS NULL
        """,
        (document_id,),
    )
    row = cur.fetchone()
    return int(row["total"] if row else 0)


def persist_text_embedding(
    cur: Any,
    *,
    source: EmbeddingSource,
    embedding: EmbeddedText,
    force_reembed: bool,
) -> bool:
    return persist_embedding(
        cur,
        source=source,
        embedding=embedding,
        force_reembed=force_reembed,
    )


def persist_embedding(
    cur: Any,
    *,
    source: EmbeddingSource,
    embedding: EmbeddedText,
    force_reembed: bool,
) -> bool:
    if len(embedding.values) != embedding.profile.dimensions:
        raise ValueError("Embedding vector dimension does not match profile.")
    existing = _active_embedding(cur, source=source, profile=embedding.profile)
    if existing and existing.get("content_sha256") == source.content_sha256 and not force_reembed:
        return False
    cur.execute(
        """
        UPDATE embeddings
        SET is_active = false,
            updated_at = now()
        WHERE owner_type = %s::embedding_owner_type_enum
          AND owner_id = %s
          AND modality = %s::modality_enum
          AND model_name = %s
          AND COALESCE(model_version, '') = %s
          AND embedding_dimensions = %s
          AND is_active
        """,
        (
            source.owner_type,
            source.owner_id,
            embedding.profile.modality,
            embedding.profile.name,
            embedding.profile.version,
            embedding.profile.dimensions,
        ),
    )
    cur.execute(
        """
        INSERT INTO embeddings
          (
            owner_type,
            owner_id,
            document_id,
            model_name,
            model_version,
            modality,
            embedding_dimensions,
            embedding,
            is_active,
            metadata_json
          )
        VALUES (
          %s::embedding_owner_type_enum,
          %s,
          %s,
          %s,
          %s,
          %s::modality_enum,
          %s,
          %s::vector,
          true,
          %s::jsonb
        )
        """,
        (
            source.owner_type,
            source.owner_id,
            source.document_id,
            embedding.profile.name,
            embedding.profile.version,
            embedding.profile.modality,
            embedding.profile.dimensions,
            vector_literal(embedding.values),
            Jsonb(
                {
                    **source.metadata,
                    "contentSha256": source.content_sha256,
                    "adapter": source.metadata.get(
                        "embeddingAdapter",
                        "deterministic_text_fixture",
                    ),
                }
            ),
        ),
    )
    return True


def _visual_descriptor(row: dict[str, Any]) -> str:
    quality = row.get("quality_json") or {}
    reasons = quality.get("reasons") if isinstance(quality, dict) else []
    reason_text = " ".join(str(reason).replace("_", " ") for reason in reasons or [])
    summary = quality.get("summary") if isinstance(quality, dict) else ""
    return " ".join(
        part
        for part in (
            str(row.get("title") or ""),
            str(row.get("original_filename") or ""),
            str(row.get("document_family") or ""),
            f"page {row.get('page_number')}",
            reason_text,
            str(summary or ""),
            "visual page image handwritten degraded scan low text layout form",
        )
        if part
    )


def _active_embedding(
    cur: Any,
    *,
    source: EmbeddingSource,
    profile: EmbeddingProfile,
) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT metadata_json ->> 'contentSha256' AS content_sha256
        FROM embeddings
        WHERE owner_type = %s::embedding_owner_type_enum
          AND owner_id = %s
          AND modality = %s::modality_enum
          AND model_name = %s
          AND COALESCE(model_version, '') = %s
          AND embedding_dimensions = %s
          AND is_active
        LIMIT 1
        """,
        (
            source.owner_type,
            source.owner_id,
            profile.modality,
            profile.name,
            profile.version,
            profile.dimensions,
        ),
    )
    return cast(dict[str, object] | None, cur.fetchone())
