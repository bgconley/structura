from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from apps.api.structura_api.dependencies import current_principal, require_csrf
from lib.auth import AuthPrincipal
from lib.contracts import AcceptedJob
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.documents.ingestion import (
    DocumentIngestionError,
    DocumentIngestionRequest,
    ingest_document_stream,
    parse_hints_json,
)
from lib.documents.list_repository import DocumentListFilters, list_document_summaries
from lib.documents.read_model import get_document_detail
from lib.extraction.repository import ExtractionRepositoryError, require_document_readable
from lib.semantic_annotations.jobs import enqueue_semantic_annotation_job
from lib.semantic_annotations.models import DocumentSemanticManifest
from lib.semantic_annotations.repository import load_current_manifest_by_mode

router = APIRouter(prefix="/api/v1", tags=["Documents"])


@router.get("/documents")
def list_documents(
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    q: str | None = None,
    family: str | None = None,
    reviewStatus: str | None = None,
    folderId: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")

    summaries, total = list_document_summaries(
        DocumentListFilters(
            access=_document_access_context(principal),
            query_text=q.strip() if q and q.strip() else None,
            family=family.strip() if family and family.strip() else None,
            review_status=reviewStatus.strip() if reviewStatus and reviewStatus.strip() else None,
            folder_id=folderId,
            limit=limit,
            offset=offset,
        )
    )
    return {
        "items": [summary.model_dump(by_alias=True) for summary in summaries],
        "total": total,
    }


@router.post(
    "/documents",
    response_model=AcceptedJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_document(
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    suppliedTitle: Annotated[str | None, Form()] = None,
    hintsJson: Annotated[str | None, Form()] = None,
) -> AcceptedJob:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")
    try:
        hints = parse_hints_json(hintsJson)
        result = ingest_document_stream(
            file.file,
            request=DocumentIngestionRequest(
                household_id=principal.household_id,
                owner_user_id=principal.user_id,
                source=source,
                filename=file.filename,
                declared_mime_type=file.content_type,
                supplied_title=suppliedTitle,
                hints=hints,
                requested_by="user",
            ),
        )
    except DocumentIngestionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
    return result.accepted_job


@router.get("/documents/{documentId}")
def get_document(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
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
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
    qualityMode: Annotated[str, Query(alias="qualityMode")] = "smart",
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


@router.post(
    "/documents/{documentId}/semantic-annotations/high-quality",
    response_model=AcceptedJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_high_quality_semantic_annotation(
    documentId: UUID,
    principal: Annotated[AuthPrincipal, Depends(require_csrf)],
) -> AcceptedJob:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        require_document_readable(documentId, _document_access_context(principal))
    except ExtractionRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        ) from exc
    with db_connection() as conn:
        with conn.cursor() as cur:
            job_id = enqueue_semantic_annotation_job(
                cur,
                document_id=documentId,
                household_id=principal.household_id,
                quality_mode="high_quality",
                requested_by="user",
                priority=26,
                reason="phase8_5.user_high_quality_pass",
            )
        conn.commit()
    return AcceptedJob.model_validate({"jobId": job_id, "status": "queued"})


def _document_access_context(principal: AuthPrincipal) -> DocumentAccessContext:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household required")
    return DocumentAccessContext(
        household_id=principal.household_id,
        user_id=principal.user_id,
        household_role=principal.household_role,
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
