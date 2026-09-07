"""Bounded local original-byte inspection shared by source verification adapters."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lib.document_parsing.structure import SourceMediaType

MAX_ORIGINAL_BYTES = 100 * 1024 * 1024


def original_metadata(path: Path) -> tuple[str, int, SourceMediaType]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        header = stream.read(16)
        digest.update(header)
        total += len(header)
        while chunk := stream.read(min(1024 * 1024, MAX_ORIGINAL_BYTES - total + 1)):
            total += len(chunk)
            if total > MAX_ORIGINAL_BYTES:
                raise ValueError("Original exceeds supported byte budget.")
            digest.update(chunk)
    mime: SourceMediaType
    if header.startswith(b"%PDF-"):
        mime = "application/pdf"
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif header.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif header.startswith((b"II\x2a\x00", b"MM\x00\x2a")):
        mime = "image/tiff"
    elif header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("Original MIME signature is unsupported.")
    return digest.hexdigest(), total, mime
