"""Bounded PDFium/Pillow source access; no layout model or placeholder rendering."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import UUID

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image, ImageOps

from lib.document_parsing.structure import (
    SourceInventory,
    SourceMediaType,
    SourcePage,
    SourceRender,
)


class DocumentSourceError(Exception):
    """Original cannot be safely inspected/rendered; never contains source text/paths."""


SOURCE_RENDERER_VERSION = "native-source-raster-v1"


def renderer_identity(mime_type: SourceMediaType) -> tuple[str, str]:
    if mime_type == "application/pdf":
        return "pdfium", f"{SOURCE_RENDERER_VERSION}/pypdfium2-{version('pypdfium2')}"
    if mime_type in {"image/png", "image/jpeg", "image/tiff", "image/webp"}:
        return "pillow-exif-oriented", f"{SOURCE_RENDERER_VERSION}/Pillow-{version('Pillow')}"
    raise DocumentSourceError("Original media type is not supported.")


@dataclass(frozen=True)
class RenderedSourcePage:
    identity: SourceRender
    image_bytes: bytes


class DocumentSource:
    """Own one immutable source snapshot and release native handles on exit.

    Inventory precedes rendering/model budgets. Render one source page at a time;
    model-specific resizing belongs in the request adapter with its transform.
    """

    def __init__(
        self,
        path: Path,
        *,
        asset_id: UUID,
        expected_sha256: str,
        mime_type: SourceMediaType,
        max_bytes: int = 100 * 1024 * 1024,
        max_pages: int = 500,
    ):
        self._pdf: Any = None
        self._image: Image.Image | None = None
        try:
            with path.open("rb") as source:
                self._content = source.read(max_bytes + 1)
            if not self._content or len(self._content) > max_bytes:
                raise DocumentSourceError("Original exceeds its supported size or is empty.")
            if hashlib.sha256(self._content).hexdigest() != expected_sha256:
                raise DocumentSourceError("Original bytes do not match their registered hash.")
            if mime_type == "application/pdf":
                self._pdf = pdfium.PdfDocument(self._content)
                count = len(self._pdf)
            elif mime_type in {"image/png", "image/jpeg", "image/tiff", "image/webp"}:
                self._image = Image.open(io.BytesIO(self._content))
                count = getattr(self._image, "n_frames", 1)
            else:
                raise DocumentSourceError("Original media type is not supported.")
            if not 1 <= count <= min(max_pages, 500):
                raise DocumentSourceError("Original page count exceeds its supported limit.")
            pages = tuple(self._page_identity(number) for number in range(1, count + 1))
            self.inventory = SourceInventory(
                original_asset_id=asset_id,
                original_sha256=expected_sha256,
                mime_type=mime_type,
                byte_size=len(self._content),
                pages=pages,
            )
        except DocumentSourceError:
            self.close()
            raise
        except Exception:
            self.close()
            raise DocumentSourceError("Original cannot be opened or inventoried.") from None

    def _page_identity(self, number: int) -> SourcePage:
        if self._pdf is not None:
            page = self._pdf[number - 1]
            try:
                width, height = page.get_size()
                rotation = page.get_rotation()
                return SourcePage(
                    page_number=number,
                    width=width,
                    height=height,
                    unit="pdf_canvas",
                    rotation_degrees=rotation,
                )
            finally:
                page.close()
        assert self._image is not None
        self._image.seek(number - 1)
        width, height = self._image.size
        if self._image.getexif().get(274) in {5, 6, 7, 8}:
            width, height = height, width
        return SourcePage(page_number=number, width=width, height=height, unit="pixels")

    def render(
        self, page_number: int, *, scale: float = 2.0, max_pixels: int = 40_000_000
    ) -> RenderedSourcePage:
        if not 1 <= page_number <= len(self.inventory.pages):
            raise DocumentSourceError("Requested page is outside the original inventory.")
        if not math.isfinite(scale) or not 0 < scale <= 4:
            raise DocumentSourceError("Source rendering scale is invalid.")
        source = self.inventory.pages[page_number - 1]
        native_text = None
        try:
            if self._pdf is not None:
                if math.ceil(source.width * scale) * math.ceil(source.height * scale) > max_pixels:
                    raise DocumentSourceError("Source raster exceeds its pixel budget.")
                page = self._pdf[page_number - 1]
                try:
                    text_page = page.get_textpage()
                    try:
                        if text_page.count_chars() > 1_000_000:
                            raise DocumentSourceError(
                                "Native page text exceeds its supported budget."
                            )
                        native_text = text_page.get_text_range()
                    finally:
                        text_page.close()
                    bitmap = page.render(scale=scale)
                    try:
                        raster = bitmap.to_pil().convert("RGB")
                    finally:
                        bitmap.close()
                finally:
                    page.close()
                renderer, renderer_version = renderer_identity("application/pdf")
            else:
                if source.width * source.height > max_pixels:
                    raise DocumentSourceError("Source image exceeds its pixel budget.")
                assert self._image is not None
                self._image.seek(page_number - 1)
                raster = ImageOps.exif_transpose(self._image).convert("RGB")
                renderer, renderer_version = renderer_identity(self.inventory.mime_type)
            try:
                buffer = io.BytesIO()
                raster.save(buffer, format="PNG")
                pixels = buffer.getvalue()
                identity = SourceRender(
                    page_number=page_number,
                    image_sha256=hashlib.sha256(pixels).hexdigest(),
                    pixel_width=raster.width,
                    pixel_height=raster.height,
                    renderer=renderer,
                    renderer_version=renderer_version,
                    native_text=native_text,
                    native_text_origin="pdf_native" if native_text is not None else None,
                )
                return RenderedSourcePage(identity, pixels)
            finally:
                raster.close()
        except DocumentSourceError:
            raise
        except Exception:
            raise DocumentSourceError("Original page cannot be rendered.") from None

    def close(self) -> None:
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None
        if self._image is not None:
            self._image.close()
            self._image = None

    def __enter__(self) -> DocumentSource:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
