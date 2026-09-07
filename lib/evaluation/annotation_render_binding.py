"""Rebind encoded reference hashes only after exact original-page pixel equality.

This pre-inference adapter does not author, correct, adjudicate or score labels.
PNG compression may differ across installed backends while RGB pixels remain
identical. The resulting annotation pins this renderer's bytes; actual capture
and source verification retain their exact encoded-byte checks.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from PIL import Image

from lib.document_parsing.source_adapter import DocumentSource, DocumentSourceError
from lib.document_parsing.structure import SourceMediaType
from lib.evaluation.annotations import AnnotatedPage, DocumentAnnotation
from lib.evaluation.identity import artifact_digest
from lib.evaluation.source_artifact_io import MAX_ORIGINAL_BYTES, original_metadata


class AnnotationRenderBindingError(Exception):
    """Static, content-free failure; no partial rebinding is returned."""


@dataclass(frozen=True)
class PageRenderBinding:
    page_number: int
    reference_image_sha256: str
    rebound_image_sha256: str
    rgb8_sha256: str
    pixel_width: int
    pixel_height: int
    renderer: str
    renderer_version: str


@dataclass(frozen=True)
class AnnotationRenderBindingRecord:
    original_annotation_sha256: str
    rebound_annotation_sha256: str
    original_sha256: str
    original_byte_size: int
    original_mime_type: SourceMediaType
    source_inventory_sha256: str
    render_scale: float
    pages: tuple[PageRenderBinding, ...]
    operation: Literal["lossless_render_encoding_rebind_v1"] = "lossless_render_encoding_rebind_v1"
    label_changes: Literal["none"] = "none"


@dataclass(frozen=True)
class ReboundAnnotation:
    annotation: DocumentAnnotation
    record: AnnotationRenderBindingRecord


def rebind_annotation_renders(
    annotation: DocumentAnnotation,
    *,
    original_path: Path,
    original_asset_id: UUID,
    reference_page_paths: Mapping[int, Path],
    render_scale: float = 2,
) -> ReboundAnnotation:
    """Verify all immutable reference PNGs and source pages before returning a copy.

    Call and freeze both annotations plus this transform record before inference.
    The adapter cannot attest when a caller invokes it. References must be ordinary
    opaque RGB PNG rasters without orientation/color transforms; no alpha discard,
    resampling, tolerance, label regeneration or model/network request is allowed.
    """
    try:
        if set(reference_page_paths) != {page.page_number for page in annotation.pages}:
            raise ValueError("Reference page inventory differs from the annotation.")
        digest, byte_size, mime = original_metadata(original_path)
        if digest != annotation.original_sha256:
            raise ValueError("Original does not match its annotation.")
        with DocumentSource(
            original_path,
            asset_id=original_asset_id,
            expected_sha256=digest,
            mime_type=mime,
            max_bytes=MAX_ORIGINAL_BYTES,
            max_pages=500,
        ) as source:
            if len(source.inventory.pages) != len(annotation.pages):
                raise ValueError("Source page inventory differs from the annotation.")
            records = tuple(
                _bind_page(
                    page,
                    reference_path=reference_page_paths[page.page_number],
                    source=source,
                    render_scale=render_scale,
                )
                for page in annotation.pages
            )
            inventory_digest = artifact_digest(source.inventory)
        pages = tuple(
            page.model_copy(update={"image_sha256": record.rebound_image_sha256})
            for page, record in zip(annotation.pages, records, strict=True)
        )
        rebound = annotation.model_copy(update={"pages": pages})
        return ReboundAnnotation(
            rebound,
            AnnotationRenderBindingRecord(
                artifact_digest(annotation),
                artifact_digest(rebound),
                digest,
                byte_size,
                mime,
                inventory_digest,
                render_scale,
                records,
            ),
        )
    except (OSError, ValueError, DocumentSourceError, Image.DecompressionBombError):
        raise AnnotationRenderBindingError(
            "Annotated source renders could not be rebound."
        ) from None


def _bind_page(
    page: AnnotatedPage,
    *,
    reference_path: Path,
    source: DocumentSource,
    render_scale: float,
) -> PageRenderBinding:
    with reference_path.open("rb") as reference:
        encoded = reference.read(MAX_ORIGINAL_BYTES + 1)
    if (
        len(encoded) > MAX_ORIGINAL_BYTES
        or hashlib.sha256(encoded).hexdigest() != page.image_sha256
    ):
        raise ValueError("Reference image differs from its annotated hash.")
    size = (page.pixel_width, page.pixel_height)
    reference_pixels = _rgb_pixels(encoded, size)
    rendered = source.render(page.page_number, scale=render_scale)
    if _rgb_pixels(rendered.image_bytes, size) != reference_pixels:
        raise ValueError("Source pixels differ from the labelled reference.")
    return PageRenderBinding(
        page.page_number,
        page.image_sha256,
        rendered.identity.image_sha256,
        hashlib.sha256(reference_pixels).hexdigest(),
        *size,
        rendered.identity.renderer,
        rendered.identity.renderer_version,
    )


def _rgb_pixels(encoded: bytes, expected_size: tuple[int, int]) -> bytes:
    with Image.open(io.BytesIO(encoded)) as image:
        if (
            image.format != "PNG"
            or image.mode != "RGB"
            or image.size != expected_size
            or image.width * image.height > 40_000_000
            or getattr(image, "n_frames", 1) != 1
            or image.getexif().get(274, 1) != 1
            or any(
                key in image.info
                for key in ("transparency", "icc_profile", "gamma", "chromaticity")
            )
        ):
            raise ValueError("Reference must be an unambiguous bounded RGB PNG page raster.")
        return image.tobytes()
