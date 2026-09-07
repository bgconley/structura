"""Protected explicit-generation evidence; no ordinary current Viewer selection."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from apps.api.structura_api.dependencies import require_document_read
from lib.auth import AuthPrincipal
from lib.documents.access_policy import DocumentAccessContext
from lib.evidence.media import VerifiedRender
from lib.evidence.models import GenerationEvidenceManifest, GenerationEvidencePage
from lib.evidence.read_service import GenerationEvidenceReader

router = APIRouter(prefix="/api/v1/documents", tags=["Generation Evidence"])
Principal = Annotated[AuthPrincipal, Depends(require_document_read)]


def _reader() -> GenerationEvidenceReader:
    return GenerationEvidenceReader()


Reader = Annotated[GenerationEvidenceReader, Depends(_reader)]


def _access(principal: AuthPrincipal) -> DocumentAccessContext:
    if not principal.household_id:
        raise HTTPException(status_code=404, detail="Retained generation is unavailable.")
    return DocumentAccessContext(
        household_id=principal.household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
        api_token_id=principal.api_token_id,
        scopes=principal.scopes,
    )


@router.get(
    "/{documentId}/parse-generations/{parseGenerationId}", response_model=GenerationEvidenceManifest
)
def generation_manifest(
    documentId: UUID,
    parseGenerationId: UUID,
    principal: Principal,
    reader: Reader,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> GenerationEvidenceManifest:
    return reader.manifest(
        documentId, parseGenerationId, _access(principal), offset=offset, limit=limit
    )


@router.get(
    "/{documentId}/parse-generations/{parseGenerationId}/pages/{pageNumber}",
    response_model=GenerationEvidencePage,
)
def generation_page(
    documentId: UUID,
    parseGenerationId: UUID,
    pageNumber: int,
    principal: Principal,
    reader: Reader,
) -> GenerationEvidencePage:
    return reader.page(documentId, parseGenerationId, pageNumber, _access(principal))


@router.get("/{documentId}/parse-generations/{parseGenerationId}/pages/{pageNumber}/render")
def generation_render(
    documentId: UUID,
    parseGenerationId: UUID,
    pageNumber: int,
    principal: Principal,
    reader: Reader,
) -> StreamingResponse:
    verified = reader.render(documentId, parseGenerationId, pageNumber, _access(principal))
    return VerifiedRenderResponse(verified)


class VerifiedRenderResponse(StreamingResponse):
    """The private spool closes even if transport fails before iteration starts."""

    def __init__(self, verified: VerifiedRender) -> None:
        self.verified = verified
        super().__init__(
            verified.chunks(),
            media_type="image/png",
            headers={
                "Content-Length": str(verified.byte_size),
                "Content-Disposition": 'inline; filename="source-page.png"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.verified.close()
