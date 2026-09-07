"""Optional bounded local source verification, separate from DB reads and inference."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from lib.document_parsing.source_adapter import DocumentSource, DocumentSourceError
from lib.evaluation.capture_models import CaptureIntegrityError, PersistedGenerationCapture

MAX_ORIGINAL_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class ArtifactVerification:
    original_asset_id: UUID
    original_sha256: str
    verified_pages: int
    original_bytes: Literal["verified"] = "verified"
    rendered_source_identity: Literal["reproduced"] = "reproduced"
    source_pixel_support: Literal["not_evaluated"] = "not_evaluated"
    invocation_authenticity: Literal["not_evaluated"] = "not_evaluated"


def verify_capture_source(
    captured: PersistedGenerationCapture,
    *,
    original_asset_id: UUID,
    original_path: Path,
) -> ArtifactVerification:
    """Explicit local path only; no URI resolution, network, fallback or model calls.

    DocumentSource rechecks the exact hash on its own bounded source snapshot,
    then reproduces each recorded render at its frozen scale. Historical renderer
    differences fail explicitly; they do not silently select a newer source.
    """
    try:
        registered = captured.source
        inventory = captured.capture.structure.source
        if original_asset_id != registered.original_asset_id or (
            registered.original_asset_id,
            registered.original_sha256,
            registered.mime_type,
            registered.byte_size,
        ) != (
            inventory.original_asset_id,
            inventory.original_sha256,
            inventory.mime_type,
            inventory.byte_size,
        ):
            raise ValueError("Original identity differs from stored source.")
        digest, byte_size, detected_mime = _original_metadata(original_path)
        if (digest, byte_size, detected_mime) != (
            registered.original_sha256,
            registered.byte_size,
            registered.mime_type,
        ):
            raise ValueError("Original metadata mismatch.")
        with DocumentSource(
            original_path,
            asset_id=original_asset_id,
            expected_sha256=digest,
            mime_type=registered.mime_type,
            max_bytes=MAX_ORIGINAL_BYTES,
            max_pages=500,
        ) as source:
            if source.inventory != inventory:
                raise ValueError("Original page inventory differs from stored source.")
            for page in captured.capture.structure.pages:
                rendered = source.render(
                    page.page_number, scale=captured.capture.configuration.render_scale
                )
                if rendered.identity != page.source:
                    raise ValueError("Recorded source render cannot be reproduced exactly.")
        return ArtifactVerification(
            original_asset_id=original_asset_id,
            original_sha256=digest,
            verified_pages=len(inventory.pages),
        )
    except (OSError, ValueError, DocumentSourceError):
        raise CaptureIntegrityError("Original or source renders could not be verified.") from None


def _original_metadata(path: Path) -> tuple[str, int, str]:
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
