"""Uploaded document metadata and signature validation at the file boundary."""

import json
import mimetypes
from pathlib import Path

from lib.documents.ingestion_models import DocumentIngestionError
from lib.storage import StagedObject

ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
EXTENSION_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}
UPLOAD_SOURCES = {
    "web_upload",
    "api_upload",
    "mobile_scan",
    "watched_folder",
    "email_import",
    "bulk_import",
}


def parse_hints_json(hints_json: str | None) -> dict[str, object]:
    if not hints_json:
        return {}
    try:
        parsed = json.loads(hints_json)
    except json.JSONDecodeError as exc:
        raise DocumentIngestionError(422, "hintsJson must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise DocumentIngestionError(422, "hintsJson must encode a JSON object")
    return parsed


def validate_upload_mime(
    *,
    declared_mime: str | None,
    filename: str,
    staged: StagedObject,
) -> str:
    with staged.temp_path.open("rb") as source:
        header = source.read(16)
    sniffed = sniff_mime(header)
    suffix = Path(filename).suffix.lower()
    extension_mime = EXTENSION_MIME_TYPES.get(suffix)
    declared = (declared_mime or "").split(";")[0].strip().lower() or None

    mime_type = sniffed or declared or extension_mime or mimetypes.guess_type(filename)[0]
    if not mime_type or mime_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise DocumentIngestionError(415, "Only PDF and common image uploads are supported")
    if extension_mime and sniffed and extension_mime != sniffed:
        raise DocumentIngestionError(415, "File extension does not match file content")
    return mime_type


def sniff_mime(header: bytes) -> str | None:
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def safe_original_filename(filename: str | None) -> str:
    candidate = Path(filename or "uploaded-document").name
    candidate = candidate.replace("\r", "").replace("\n", "").strip()
    return candidate or "uploaded-document"


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled document"
