"""Authenticated legacy multipart adapter with bounded IO and owned spool cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import HTTPException
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect, Request

LEGACY_ENVELOPE_BYTES = 64 * 1024
CONTROL_FIELD_BYTES = 16 * 1024
TRANSFER_DEADLINE_SECONDS = 10 * 60
TRANSFER_IDLE_SECONDS = 30


@dataclass(frozen=True)
class DocumentUploadForm:
    file: UploadFile
    source: str
    supplied_title: str | None
    hints_json: str | None


class _UploadParser(MultiPartParser):
    """Keep Starlette multipart internals and their cleanup lifecycle in one adapter."""

    def __init__(self, request: Request, stream: AsyncGenerator[bytes, None], file_limit: int):
        super().__init__(
            request.headers, stream, max_files=1, max_fields=3, max_part_size=CONTROL_FIELD_BYTES
        )
        self.file_limit = file_limit
        self.file_bytes = 0
        self.header_bytes = 0
        self.complete = False

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self.file_bytes += end - start
            if self.file_bytes > self.file_limit:
                raise HTTPException(413, "The upload exceeds the supported size.")
        elif len(self._current_part.data) + end - start > CONTROL_FIELD_BYTES:
            raise HTTPException(413, "The upload exceeds the supported size.")
        super().on_part_data(data, start, end)

    def _count_header(self, size: int) -> None:
        self.header_bytes += size
        if self.header_bytes > CONTROL_FIELD_BYTES:
            raise HTTPException(413, "The upload exceeds the supported size.")

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._count_header(end - start)
        super().on_header_field(data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._count_header(end - start)
        super().on_header_value(data, start, end)

    def on_end(self) -> None:
        self.complete = True
        super().on_end()

    def close_spools(self) -> None:
        # Starlette only closes this list on MultiPartException. Our byte/deadline
        # failures, disconnects and cancellations must also close unfinished parts.
        for spool in self._files_to_close_on_error:
            spool.close()


def _declared_length(request: Request, body_limit: int) -> int | None:
    lengths = request.headers.getlist("content-length")
    if not lengths:
        return None
    if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
        raise HTTPException(400, "Invalid request.")
    if len(lengths[0]) > 20:
        raise HTTPException(413, "The upload exceeds the supported size.")
    length = int(lengths[0])
    if length > body_limit:
        raise HTTPException(413, "The upload exceeds the supported size.")
    return length


async def _bounded_body(
    request: Request, body_limit: int, declared_length: int | None
) -> AsyncGenerator[bytes, None]:
    received = 0
    deadline = asyncio.get_running_loop().time() + TRANSFER_DEADLINE_SECONDS
    stream = request.stream().__aiter__()
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise HTTPException(408, "The upload did not complete in time.")
        try:
            chunk = await asyncio.wait_for(anext(stream), min(remaining, TRANSFER_IDLE_SECONDS))
        except StopAsyncIteration:
            break
        except TimeoutError as exc:
            raise HTTPException(408, "The upload did not complete in time.") from exc
        except ClientDisconnect as exc:
            raise HTTPException(400, "Invalid request.") from exc
        received += len(chunk)
        if received > body_limit:
            raise HTTPException(413, "The upload exceeds the supported size.")
        if declared_length is not None and received > declared_length:
            raise HTTPException(400, "Invalid request.")
        # Bound parser callbacks even when the server supplies one large ASGI chunk.
        for start in range(0, len(chunk), 64 * 1024):
            yield chunk[start : start + 64 * 1024]
    if declared_length is not None and received != declared_length:
        raise HTTPException(400, "Invalid request.")


def _fields(form: FormData) -> DocumentUploadForm:
    values: dict[str, str | UploadFile] = {}
    for key, value in form.multi_items():
        if key in values or key not in {"file", "source", "suppliedTitle", "hintsJson"}:
            raise HTTPException(422, "Invalid request value.")
        values[key] = value
    file, source = values.get("file"), values.get("source")
    title, hints = values.get("suppliedTitle"), values.get("hintsJson")
    if (
        not isinstance(file, UploadFile)
        or not isinstance(source, str)
        or isinstance(title, UploadFile)
        or isinstance(hints, UploadFile)
    ):
        raise HTTPException(422, "Invalid request value.")
    return DocumentUploadForm(file, source, title, hints)


@asynccontextmanager
async def read_document_upload(
    request: Request, *, file_limit: int
) -> AsyncIterator[DocumentUploadForm]:
    """Call only after authentication; keep the context open through intake IO."""
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or len(content_types[0]) > CONTROL_FIELD_BYTES:
        raise HTTPException(400, "Invalid request.")
    media_type, options = parse_options_header(content_types[0])
    boundary = options.get(b"boundary", b"")
    if media_type != b"multipart/form-data" or not boundary or len(boundary) > 200:
        raise HTTPException(400, "Invalid request.")
    body_limit = file_limit + LEGACY_ENVELOPE_BYTES
    declared = _declared_length(request, body_limit)
    parser = _UploadParser(request, _bounded_body(request, body_limit, declared), file_limit)
    try:
        try:
            form = await parser.parse()
            if not parser.complete:
                raise HTTPException(400, "Invalid request.")
        except (MultiPartException, MultipartParseError, LookupError, UnicodeError) as exc:
            raise HTTPException(400, "Invalid request.") from exc
        yield _fields(form)
    finally:
        parser.close_spools()
