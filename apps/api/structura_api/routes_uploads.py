"""Raw request transport: authenticate/admit before consuming any file bytes."""

import json
from functools import partial
from typing import Annotated
from uuid import UUID

from anyio import fail_after
from anyio.to_thread import run_sync
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from apps.api.structura_api.dependencies import require_document_read, require_document_write
from lib.auth import AuthPrincipal
from lib.auth.request_authority import RequestCredential
from lib.uploads.errors import UploadError
from lib.uploads.models import UploadAttempt, UploadCreate, UploadDecision
from lib.uploads.operation_repository import cancel_attempt, create_attempt
from lib.uploads.policy import UploadPolicy, UploadPolicyRead
from lib.uploads.read_repository import read_attempt
from lib.uploads.service import UploadService

router = APIRouter(prefix="/api/v1", tags=["uploads"])


async def _control(request: Request, maximum: int) -> object:
    body = bytearray()
    try:
        with fail_after(30):
            async for chunk in request.stream():
                if len(body) + len(chunk) > maximum:
                    raise UploadError("upload_control_too_large")
                body.extend(chunk)
    except TimeoutError as exc:
        raise UploadError("upload_timed_out") from exc
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise HTTPException(422, "Invalid upload command.") from exc


def _uuid_header(request: Request, name: str, *, optional: bool = False) -> UUID | None:
    value = request.headers.get(name)
    if value is None and optional:
        return None
    try:
        return UUID((value or "").strip('"'))
    except ValueError as exc:
        raise HTTPException(422, "An exact upload revision is required.") from exc


@router.get("/upload-policy", response_model=UploadPolicyRead)
def upload_policy(_: Annotated[AuthPrincipal, Depends(require_document_read)]) -> UploadPolicyRead:
    return UploadPolicy().public()


@router.post("/uploads", response_model=UploadAttempt)
async def register_upload(
    request: Request, principal: Annotated[AuthPrincipal, Depends(require_document_write)]
) -> UploadAttempt:
    policy = UploadPolicy()
    try:
        command = UploadCreate.model_validate(await _control(request, policy.control_bytes))
    except ValidationError as exc:
        raise HTTPException(422, "Invalid upload command.") from exc
    return await run_sync(
        create_attempt, command, RequestCredential.from_principal(principal), policy
    )


@router.get("/uploads/{uploadId}", response_model=UploadAttempt)
def get_upload(
    uploadId: UUID, principal: Annotated[AuthPrincipal, Depends(require_document_read)]
) -> UploadAttempt:
    return read_attempt(uploadId, RequestCredential.from_principal(principal))


@router.put("/uploads/{uploadId}/content", response_model=UploadAttempt)
async def put_upload_content(
    uploadId: UUID,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_document_write)],
) -> UploadAttempt:
    revision = _uuid_header(request, "if-match")
    if revision is None:
        raise HTTPException(422, "An exact upload revision is required.")
    replacement = _uuid_header(request, "x-replace-transfer-id", optional=True)
    # Construction establishes/fsyncs staging directories; keep it off the loop.
    service = await run_sync(UploadService)
    return await service.receive(
        uploadId,
        revision,
        RequestCredential.from_principal(principal),
        request.stream(),
        replace_transfer_id=replacement,
        declared_length=_content_length(request),
    )


@router.post("/uploads/{uploadId}/decision", response_model=UploadAttempt)
async def decide_upload(
    uploadId: UUID,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_document_write)],
) -> UploadAttempt:
    policy = UploadPolicy()
    try:
        command = UploadDecision.model_validate(await _control(request, policy.control_bytes))
    except ValidationError as exc:
        raise HTTPException(422, "Invalid upload decision.") from exc
    service = await run_sync(partial(UploadService, policy=policy))
    return await run_sync(
        partial(service.decide, uploadId, command, RequestCredential.from_principal(principal))
    )


@router.delete("/uploads/{uploadId}", response_model=UploadAttempt)
def delete_upload(
    uploadId: UUID, principal: Annotated[AuthPrincipal, Depends(require_document_write)]
) -> UploadAttempt:
    return cancel_attempt(uploadId, RequestCredential.from_principal(principal))


def _content_length(request: Request) -> int | None:
    values = request.headers.getlist("content-length")
    if not values:
        return None
    if len(values) != 1 or not values[0].isascii() or not values[0].isdecimal():
        raise HTTPException(422, "Invalid upload byte count.")
    if len(values[0]) > 12:
        raise UploadError("upload_too_large")
    return int(values[0])
