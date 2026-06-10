from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from lib.config import get_settings
from lib.jobs import create_job_with_cursor
from lib.model_runtime.profiles import TEXT_EMBED_PROFILE, VISUAL_EMBED_PROFILE


def enqueue_embed_document_job(
    cur: Any,
    *,
    document_id: UUID,
    household_id: UUID | None = None,
    force_reembed: bool = False,
    modalities: tuple[str, ...] = ("text",),
    owner_types: tuple[str, ...] | None = None,
    model_profile: str | None = None,
    queue_name: str = "embeddings",
    priority: int = 32,
) -> UUID | None:
    requested_modalities = list(dict.fromkeys(modalities or ("text",)))
    if "visual" not in requested_modalities and not get_settings().embedding_text_enabled:
        # Text embeddings are de-scoped by the operator; skip enqueueing so the
        # `embeddings` queue does not grow without a worker or model service.
        return None
    if household_id is None:
        cur.execute("SELECT household_id FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
        household_id = row["household_id"] if row else None
    job_id = uuid4()
    payload = {
        "schema_name": "embed_document_job",
        "schema_version": "v1",
        "job_id": str(job_id),
        "created_at": datetime.now(UTC).isoformat(),
        "attempt": 1,
        "priority": priority,
        "document_id": str(document_id),
        "modalities": requested_modalities,
        "model_profile": model_profile or _model_profile_for_modalities(requested_modalities),
        "force_reembed": force_reembed,
    }
    if owner_types:
        payload["owner_types"] = list(owner_types)
    create_job_with_cursor(
        cur,
        job_id=job_id,
        job_type="embed",
        household_id=household_id,
        document_id=document_id,
        payload=payload,
        priority=priority,
        queue_name=queue_name,
    )
    return job_id


def enqueue_visual_embed_document_job(
    cur: Any,
    *,
    document_id: UUID,
    household_id: UUID | None = None,
    force_reembed: bool = False,
    priority: int = 34,
) -> UUID | None:
    return enqueue_embed_document_job(
        cur,
        document_id=document_id,
        household_id=household_id,
        force_reembed=force_reembed,
        modalities=("visual",),
        owner_types=("page", "asset"),
        model_profile=None,
        queue_name="visual-embeddings",
        priority=priority,
    )


def _model_profile_for_modalities(modalities: list[str]) -> str:
    settings = get_settings()
    if settings.model_mode != "fixture":
        if modalities == ["visual"]:
            return settings.visual_embed_profile or VISUAL_EMBED_PROFILE
        if "visual" in modalities:
            return settings.visual_embed_profile or VISUAL_EMBED_PROFILE
        return settings.text_embed_profile or TEXT_EMBED_PROFILE
    if modalities == ["visual"]:
        return "structura-fixture-visual-byte-embedding:v1"
    if "visual" in modalities:
        return "structura-fixture-mixed-text-visual-embedding:v1"
    return "structura-fixture-text-embedding:v1"
