from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.documents.assets import upsert_current_asset
from lib.documents.parse_models import CanonicalParseResult, PersistedParseSummary
from lib.documents.parse_repository import replace_relational_parse, update_document_parse_state
from lib.storage import ObjectStorage, StoredObject


def persist_canonical_parse(
    *,
    document_id: UUID,
    result: CanonicalParseResult,
    source_asset_id: UUID,
    source_sha256: str,
    job_id: UUID | None = None,
    storage: ObjectStorage | None = None,
) -> PersistedParseSummary:
    object_storage = storage or ObjectStorage()
    created_objects: list[StoredObject] = []
    try:
        docling_object = object_storage.store_bytes(
            result.json_bytes,
            kind="derived",
            role=f"docling-json-{document_id}",
        )
        _remember_created(created_objects, docling_object)
        markdown_object = (
            object_storage.store_bytes(
                result.markdown_bytes,
                kind="derived",
                role=f"docling-md-{document_id}",
            )
            if result.markdown_bytes
            else None
        )
        _remember_created(created_objects, markdown_object)
        html_object = (
            object_storage.store_bytes(
                result.html_bytes,
                kind="derived",
                role=f"docling-html-{document_id}",
            )
            if result.html_bytes
            else None
        )
        _remember_created(created_objects, html_object)

        with db_connection() as conn:
            with conn.cursor() as cur:
                _lock_household_document(cur, document_id)
                common_metadata = {
                    "phase": "phase3",
                    "sourceAssetId": str(source_asset_id),
                    "sourceSha256": source_sha256,
                    "jobId": str(job_id) if job_id else None,
                    "converter": {
                        "name": result.converter_name,
                        "version": result.converter_version,
                    },
                    "warnings": result.warnings,
                    **dict(result.metadata),
                }
                docling_asset_id = _persist_artifact_asset(
                    cur,
                    document_id=document_id,
                    asset_role="docling_json",
                    stored=docling_object,
                    mime_type="application/json",
                    metadata={**common_metadata, "artifactKind": "docling_json"},
                    model_name=result.converter_name,
                    model_version=result.converter_version,
                )
                markdown_asset_id = (
                    _persist_artifact_asset(
                        cur,
                        document_id=document_id,
                        asset_role="docling_md",
                        stored=markdown_object,
                        mime_type="text/markdown; charset=utf-8",
                        metadata={**common_metadata, "artifactKind": "docling_md"},
                        model_name=result.converter_name,
                        model_version=result.converter_version,
                    )
                    if markdown_object
                    else None
                )
                html_asset_id = (
                    _persist_artifact_asset(
                        cur,
                        document_id=document_id,
                        asset_role="docling_html",
                        stored=html_object,
                        mime_type="text/html; charset=utf-8",
                        metadata={**common_metadata, "artifactKind": "docling_html"},
                        model_name=result.converter_name,
                        model_version=result.converter_version,
                    )
                    if html_object
                    else None
                )
                replace_relational_parse(cur, document_id, result)
                update_document_parse_state(
                    cur,
                    document_id=document_id,
                    docling_asset_id=docling_asset_id,
                    result=result,
                    job_id=job_id,
                )
            conn.commit()
    except Exception:
        _cleanup_created_objects(created_objects)
        raise

    return PersistedParseSummary(
        docling_asset_id=docling_asset_id,
        markdown_asset_id=markdown_asset_id,
        html_asset_id=html_asset_id,
        page_count=len(result.pages),
        element_count=len(result.elements),
        table_count=len(result.tables),
        chunk_count=len(result.chunks),
    )


def _remember_created(objects: list[StoredObject], stored: StoredObject | None) -> None:
    if stored and stored.created:
        objects.append(stored)


def _cleanup_created_objects(objects: list[StoredObject]) -> None:
    for stored in objects:
        with suppress(OSError):
            stored.path.unlink(missing_ok=True)


def mark_parse_failed(
    *,
    document_id: UUID,
    error_class: str,
    message: str,
    job_id: UUID | None = None,
) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE documents
                SET metadata_json = metadata_json || %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                  AND deleted_at IS NULL
                """,
                (
                    Jsonb(
                        {
                            "phase3": {
                                "parseStatus": "failed",
                                "lastDoclingJobId": str(job_id) if job_id else None,
                                "errorClass": error_class,
                                "errorMessage": message,
                            }
                        }
                    ),
                    document_id,
                ),
            )
        conn.commit()


def _persist_artifact_asset(
    cur: Any,
    *,
    document_id: UUID,
    asset_role: str,
    stored: StoredObject,
    mime_type: str,
    metadata: Mapping[str, Any],
    model_name: str,
    model_version: str,
) -> UUID:
    return upsert_current_asset(
        cur,
        document_id=document_id,
        asset_role=asset_role,
        uri=stored.uri,
        mime_type=mime_type,
        byte_size=stored.byte_size,
        sha256=stored.sha256,
        metadata=metadata,
        model_name=model_name,
        model_version=model_version,
    )


def _lock_household_document(cur: Any, document_id: UUID) -> None:
    cur.execute(
        """
        SELECT id
        FROM documents
        WHERE id = %s
          AND deleted_at IS NULL
        FOR UPDATE
        """,
        (document_id,),
    )
    if not cur.fetchone():
        raise ValueError("Document not found.")
