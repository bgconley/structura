from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from apps.api.structura_api.dependencies import require_document_read, require_document_write
from apps.api.structura_api.document_upload_form import read_document_upload
from lib.auth import AuthPrincipal
from lib.config import get_settings
from lib.contracts import AcceptedDocumentUpload, DocumentListResponse
from lib.documents.access_policy import DocumentAccessContext
from lib.documents.browse_query import MAX_BROWSE_OFFSET, DocumentSort, InboxState
from lib.documents.ingestion import (
    DocumentIngestionError,
    DocumentIngestionRequest,
    ingest_document_stream,
    parse_hints_json,
)
from lib.documents.list_repository import DocumentListFilters, list_document_summaries
from lib.documents.read_model import get_document_detail
from lib.extraction.repository import ExtractionRepositoryError, require_document_readable
from lib.semantic_annotations.models import DocumentSemanticManifest, QualityMode
from lib.semantic_annotations.repository import load_current_manifest_by_mode

router = APIRouter(prefix="/api/v1", tags=["Documents"])


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
    q: str | None = None,
    family: str | None = None,
    reviewStatus: str | None = None,
    folderId: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=MAX_BROWSE_OFFSET)] = 0,
    inboxState: InboxState = InboxState.ALL,
    sort: DocumentSort = DocumentSort.UPLOADED_DESC,
) -> DocumentListResponse:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")

    return list_document_summaries(
        DocumentListFilters(
            access=_document_access_context(principal),
            query_text=q.strip() if q and q.strip() else None,
            family=family.strip() if family and family.strip() else None,
            review_status=reviewStatus.strip() if reviewStatus and reviewStatus.strip() else None,
            folder_id=folderId,
            limit=limit,
            offset=offset,
            inbox_state=inboxState,
            sort=sort,
        )
    )


@router.post(
    "/documents",
    response_model=AcceptedDocumentUpload,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_document(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_document_write)],
) -> AcceptedDocumentUpload:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")
    try:
        async with read_document_upload(
            request, file_limit=get_settings().max_upload_bytes
        ) as form:
            result = await run_in_threadpool(
                ingest_document_stream,
                form.file.file,
                request=DocumentIngestionRequest(
                    household_id=principal.household_id,
                    owner_user_id=principal.user_id,
                    source=form.source,
                    filename=form.file.filename,
                    declared_mime_type=form.file.content_type,
                    supplied_title=form.supplied_title,
                    hints=parse_hints_json(form.hints_json),
                    requested_by="user",
                ),
            )
    except DocumentIngestionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
    return AcceptedDocumentUpload(
        jobId=result.accepted_job.job_id,
        status=result.accepted_job.status,
        documentId=result.document_id,
    )


@router.get("/documents/{documentId}")
def get_document(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
) -> dict[str, object]:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    document = get_document_detail(documentId, _document_access_context(principal))
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document.model_dump(by_alias=True)


@router.get("/documents/{documentId}/semantic-annotations/current")
def get_current_semantic_annotation(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_document_read)],
    qualityMode: Annotated[QualityMode, Query(alias="qualityMode")] = "smart",
) -> dict[str, object]:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        require_document_readable(documentId, _document_access_context(principal))
    except ExtractionRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    manifest = load_current_manifest_by_mode(
        document_id=documentId,
        quality_mode=qualityMode,
    )
    return {
        "documentId": str(documentId),
        "qualityMode": qualityMode,
        "current": _semantic_manifest_payload(manifest) if manifest else None,
    }


def _require_document_readable_or_404(
    document_id: UUID,
    principal: AuthPrincipal,
) -> None:
    try:
        require_document_readable(document_id, _document_access_context(principal))
    except ExtractionRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc


def _document_access_context(principal: AuthPrincipal) -> DocumentAccessContext:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")
    return DocumentAccessContext(
        household_id=principal.household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
        api_token_id=principal.api_token_id,
        scopes=principal.scopes,
    )


def _semantic_manifest_payload(manifest: DocumentSemanticManifest) -> dict[str, object]:
    return {
        "qualityMode": manifest.quality_mode,
        "profileName": manifest.profile_name,
        "sourceEngine": manifest.source_engine,
        "modelName": manifest.model_name,
        "modelVersion": manifest.model_version,
        "promptVersion": manifest.prompt_version,
        "reviewRequired": manifest.review_required,
        "escalationReason": manifest.escalation_reason,
        "confidence": manifest.confidence,
        "pages": [
            {
                "pageId": str(page.page_id),
                "pageNumber": page.page_number,
                "pageRole": page.page_role,
                "documentTypeHint": page.document_type_hint,
                "extractionUsefulness": page.extraction_usefulness,
                "isBoilerplate": page.is_boilerplate,
                "hasStructuredTargets": page.has_structured_targets,
                "ambiguous": page.ambiguous,
                "escalationRequired": page.escalation_required,
                "reason": page.reason,
                "confidence": page.confidence,
                "metadata": page.metadata,
            }
            for page in manifest.pages
        ],
        "regions": [
            {
                "semanticType": region.semantic_type,
                "priority": region.priority,
                "graniteTask": region.granite_task,
                "targetSchema": region.target_schema,
                "expectedFields": list(region.expected_fields),
                "reviewRequired": region.review_required,
                "reason": region.reason,
                "confidence": region.confidence,
                "metadata": region.metadata,
                "grounding": {
                    "kind": region.grounding.kind,
                    "pageId": str(region.grounding.page_id) if region.grounding.page_id else None,
                    "elementId": (
                        str(region.grounding.element_id) if region.grounding.element_id else None
                    ),
                    "tableId": (
                        str(region.grounding.table_id) if region.grounding.table_id else None
                    ),
                },
            }
            for region in manifest.regions
        ],
    }
