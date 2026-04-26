from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.responses import FileResponse

from apps.api.structura_api.dependencies import current_principal
from lib.auth import AuthPrincipal
from lib.db.connection import db_connection
from lib.documents.access_policy import (
    DocumentAccessContext,
    document_read_access_params,
)
from lib.storage import InvalidObjectUri, ObjectStorage, StorageError

router = APIRouter(prefix="/api/v1", tags=["Assets"])


@router.get("/assets/{assetId}", tags=["Assets"])
def get_asset(
    assetId: UUID,
    principal: Annotated[AuthPrincipal, Depends(current_principal)],
) -> FileResponse:
    if not principal.household_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  a.id,
                  a.asset_role::text AS asset_role,
                  a.uri,
                  a.mime_type,
                  a.byte_size,
                  a.sha256,
                  d.original_filename,
                  d.title
                FROM document_assets a
                JOIN documents d ON d.id = a.document_id
                WHERE a.id = %s
                  AND d.deleted_at IS NULL
                  AND document_is_readable(d.id, %s, %s, %s)
                """,
                (
                    assetId,
                    *document_read_access_params(
                        DocumentAccessContext(
                            household_id=principal.household_id,
                            user_id=principal.user_id,
                            household_role=principal.household_role,
                        )
                    ),
                ),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    storage = ObjectStorage()
    try:
        consistency = storage.verify(
            uri=row["uri"],
            expected_sha256=row["sha256"],
            expected_size=row["byte_size"],
        )
        path = storage.path_for_uri(row["uri"])
    except (InvalidObjectUri, StorageError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        ) from None

    if not consistency.ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    filename = _download_filename(
        role=row["asset_role"],
        original_filename=row["original_filename"],
        title=row["title"],
        mime_type=row["mime_type"],
    )
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(
        path,
        media_type=row["mime_type"] or "application/octet-stream",
        filename=filename,
        content_disposition_type="inline",
        headers=headers,
    )


def _download_filename(
    *,
    role: str,
    original_filename: str | None,
    title: str,
    mime_type: str | None,
) -> str:
    if role == "original" and original_filename:
        return _safe_original_filename(original_filename)
    suffix = mimetypes.guess_extension(mime_type or "") or ".bin"
    safe_title = "".join(ch if ch.isalnum() else "-" for ch in title.lower()).strip("-")
    return f"{safe_title or 'structura-document'}-{role}{suffix}"


def _safe_original_filename(filename: str | None) -> str:
    candidate = Path(filename or "uploaded-document").name
    candidate = candidate.replace("\r", "").replace("\n", "").strip()
    return candidate or "uploaded-document"
