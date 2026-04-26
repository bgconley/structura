from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.documents.canonical_parse import (
    mark_parse_failed,
    persist_canonical_parse,
)
from lib.documents.parse_models import PersistedParseSummary
from lib.storage import ObjectStorage
from workers.docling.converter import DoclingConverter, RealDoclingConverter
from workers.previews import generate_page_previews


class DoclingWorkerError(Exception):
    pass


@dataclass(frozen=True)
class SourceDocument:
    document_id: UUID
    asset_id: UUID
    uri: str
    sha256: str
    byte_size: int
    mime_type: str
    original_filename: str


def convert_document(
    document_id: UUID,
    *,
    job_id: UUID | None = None,
    converter: DoclingConverter | None = None,
    storage: ObjectStorage | None = None,
) -> PersistedParseSummary:
    object_storage = storage or ObjectStorage(settings=get_settings())
    source = _source_document(document_id)
    consistency = object_storage.verify(
        uri=source.uri,
        expected_sha256=source.sha256,
        expected_size=source.byte_size,
    )
    if not consistency.ok:
        raise DoclingWorkerError("Original asset failed storage verification.")

    source_path = object_storage.path_for_uri(source.uri)
    active_converter = converter or RealDoclingConverter()
    result = active_converter.convert(
        source_path,
        filename=source.original_filename,
        mime_type=source.mime_type,
    )
    summary = persist_canonical_parse(
        document_id=document_id,
        result=result,
        source_asset_id=source.asset_id,
        source_sha256=source.sha256,
        job_id=job_id,
        storage=object_storage,
    )
    generate_page_previews(document_id, job_id=job_id, storage=object_storage)
    return summary


def mark_document_parse_failed(
    *,
    document_id: UUID,
    error_class: str,
    message: str,
    job_id: UUID | None = None,
) -> None:
    mark_parse_failed(
        document_id=document_id,
        error_class=error_class,
        message=message,
        job_id=job_id,
    )


def _source_document(document_id: UUID) -> SourceDocument:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  d.id AS document_id,
                  d.original_filename,
                  a.id AS asset_id,
                  a.uri,
                  a.sha256,
                  a.byte_size,
                  a.mime_type
                FROM documents d
                JOIN document_assets a ON a.document_id = d.id
                 AND a.asset_role = 'original'
                 AND a.is_current
                WHERE d.id = %s
                  AND d.deleted_at IS NULL
                """,
                (document_id,),
            )
            row = cur.fetchone()
    if not row:
        raise DoclingWorkerError("Document original asset not found.")
    return SourceDocument(
        document_id=row["document_id"],
        asset_id=row["asset_id"],
        uri=row["uri"],
        sha256=row["sha256"],
        byte_size=row["byte_size"],
        mime_type=row["mime_type"] or "application/octet-stream",
        original_filename=row["original_filename"] or "document",
    )
