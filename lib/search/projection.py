from __future__ import annotations

from uuid import UUID

from lib.db.connection import db_connection
from lib.search.embedding_repository import refresh_search_projection
from lib.search.jobs import enqueue_embed_document_job


def refresh_projection_and_enqueue_embedding(
    *,
    document_id: UUID,
    household_id: UUID | None = None,
    force_reembed: bool = False,
) -> UUID | None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            refresh_search_projection(cur, document_id)
            job_id = enqueue_embed_document_job(
                cur,
                document_id=document_id,
                household_id=household_id,
                force_reembed=force_reembed,
            )
        conn.commit()
    return job_id
