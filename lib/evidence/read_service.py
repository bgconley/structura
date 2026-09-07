"""Authorized historical evidence presentation and verified media snapshots."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import ValidationError

from lib.documents.access_policy import DocumentAccessContext
from lib.evidence.errors import EvidenceUnavailable
from lib.evidence.media import VerifiedRender, snapshot_render
from lib.evidence.models import GenerationEvidenceManifest, GenerationEvidencePage
from lib.evidence.read_mapping import (
    page_content,
    page_summary,
    render_response,
    retained_asset,
    validate_header,
)
from lib.evidence.read_repository import read_generation
from lib.storage import ObjectStorage


class GenerationEvidenceReader:
    def __init__(self, storage: ObjectStorage | None = None) -> None:
        self.storage = storage or ObjectStorage()

    def manifest(
        self,
        document_id: UUID,
        parse_generation_id: UUID,
        access: DocumentAccessContext,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> GenerationEvidenceManifest:
        row = read_generation(document_id, parse_generation_id, access, offset=offset, limit=limit)
        try:
            config = validate_header(row)
            expected_count = max(0, min(limit, row["page_count"] - offset))
            if len(row["pages"]) != expected_count:
                raise EvidenceUnavailable("Retained generation is unavailable.")
            pages = [page_summary(row, item) for item in row["pages"]]
            if [p.page_number for p in pages] != list(
                range(offset + 1, offset + expected_count + 1)
            ):
                raise EvidenceUnavailable("Retained generation is unavailable.")
            return GenerationEvidenceManifest(
                documentId=document_id,
                processingRunId=row["processing_run_id"],
                parseGenerationId=parse_generation_id,
                processingRunState=row["run_status"],
                originalAssetId=row["original_asset_id"],
                originalSha256=row["original_sha256"],
                structureSha256=row["structure_sha256"],
                inventorySha256=row["inventory_sha256"],
                parserConfiguration=config,
                renderSetState=row["render_set_state"],
                renderSetSha256=row["render_set_sha256"],
                total=row["page_count"],
                offset=offset,
                limit=limit,
                pages=pages,
                observedAt=row["observed_at"],
            )
        except (ValidationError, ValueError, KeyError, TypeError):
            raise EvidenceUnavailable("Retained generation is unavailable.") from None

    def page(
        self,
        document_id: UUID,
        parse_generation_id: UUID,
        page_number: int,
        access: DocumentAccessContext,
    ) -> GenerationEvidencePage:
        row, item = self._page_row(
            document_id, parse_generation_id, page_number, access, content=True
        )
        try:
            page, chunks = page_content(row, item)
            summary = page_summary(row, item)
            return GenerationEvidencePage(
                documentId=document_id,
                parseGenerationId=parse_generation_id,
                processingRunId=row["processing_run_id"],
                sourcePage=summary.source_page,
                page=page,
                chunks=chunks,
                render=summary.render,
            )
        except (ValidationError, ValueError, KeyError, TypeError):
            raise EvidenceUnavailable("Retained generation is unavailable.") from None

    def render(
        self,
        document_id: UUID,
        parse_generation_id: UUID,
        page_number: int,
        access: DocumentAccessContext,
    ) -> VerifiedRender:
        row, item = self._page_row(document_id, parse_generation_id, page_number, access)
        try:
            asset = retained_asset(row, item)
        except (ValidationError, ValueError, KeyError, TypeError):
            raise EvidenceUnavailable("Retained generation is unavailable.") from None
        if asset is None:
            raise EvidenceUnavailable("Retained generation is unavailable.")
        verified = snapshot_render(asset, self.storage)
        try:
            # A second independent live ACL/token snapshot follows potentially slow IO.
            # Return only the verified private spool; never reopen the original path.
            refreshed, refreshed_item = self._page_row(
                document_id, parse_generation_id, page_number, access
            )
            if render_response(
                refreshed, retained_asset(refreshed, refreshed_item)
            ) != render_response(row, asset):
                raise EvidenceUnavailable("Retained generation is unavailable.")
        except BaseException:
            verified.close()
            raise
        return verified

    @staticmethod
    def _page_row(
        document_id: UUID,
        parse_generation_id: UUID,
        page_number: int,
        access: DocumentAccessContext,
        *,
        content: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not 1 <= page_number <= 500:
            raise EvidenceUnavailable("Retained generation is unavailable.")
        row = read_generation(
            document_id,
            parse_generation_id,
            access,
            offset=page_number - 1,
            include_content=content,
        )
        try:
            validate_header(row)
            if len(row["pages"]) != 1 or row["pages"][0]["page_number"] != page_number:
                raise EvidenceUnavailable("Retained generation is unavailable.")
        except (ValidationError, ValueError, KeyError, TypeError):
            raise EvidenceUnavailable("Retained generation is unavailable.") from None
        return row, row["pages"][0]
