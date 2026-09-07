"""Signature identification only: decoding, encryption and readability are later work."""

from pathlib import Path

from lib.documents.ingestion_content import EXTENSION_MIME_TYPES, sniff_mime
from lib.uploads.errors import UploadError
from lib.uploads.models import UploadCreate, VerifiedContent


def identify_content(
    metadata: UploadCreate, header: bytes, digest: str, size: int
) -> VerifiedContent:
    if size != metadata.declared_bytes:
        raise UploadError("upload_size_mismatch")
    detected = sniff_mime(header)
    if detected is None:
        raise UploadError("upload_signature_unsupported")
    extension = EXTENSION_MIME_TYPES.get(Path(metadata.filename).suffix.lower())
    declared = (metadata.declared_mime_type or "").split(";", 1)[0].strip().lower()
    if (extension and extension != detected) or (
        declared and declared != "application/octet-stream" and declared != detected
    ):
        raise UploadError("upload_format_mismatch")
    return VerifiedContent(digest, size, detected)
