from __future__ import annotations

import hashlib
from dataclasses import asdict
from uuid import uuid4

import pytest
from PIL import Image

from lib.document_parsing.source_adapter import DocumentSource
from lib.evaluation.annotation_render_binding import (
    AnnotationRenderBindingError,
    rebind_annotation_renders,
)
from lib.evaluation.identity import artifact_digest
from tests.unit.evaluation.conftest import FIXTURES


def bind(annotation, *, paths=None, original=None):
    return rebind_annotation_renders(
        annotation,
        original_path=original or FIXTURES / "original.tiff",
        original_asset_id=uuid4(),
        reference_page_paths=paths
        or {number: FIXTURES / f"page-{number}.png" for number in (1, 2)},
    )


def repin_page(annotation, path, number=1):
    pages = list(annotation.pages)
    pages[number - 1] = pages[number - 1].model_copy(
        update={"image_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    )
    return annotation.model_copy(update={"pages": tuple(pages)})


def test_recompression_rebinds_only_hashes_and_records_exact_source_pixels(inputs, tmp_path):
    annotation = inputs[1]
    encoded = tmp_path / "reference.png"
    with Image.open(FIXTURES / "page-1.png") as reference:
        reference.save(encoded, format="PNG", compress_level=0)
        expected_pixels = reference.tobytes()
    annotation = repin_page(annotation, encoded)
    pinned = annotation.model_dump(mode="json")
    original_fixture = (FIXTURES / "annotation.json").read_bytes()
    result = bind(annotation, paths={1: encoded, 2: FIXTURES / "page-2.png"})
    assert annotation.model_dump(mode="json") == pinned
    assert (FIXTURES / "annotation.json").read_bytes() == original_fixture
    rebound_payload = result.annotation.model_dump(mode="json")
    for before, after in zip(pinned["pages"], rebound_payload["pages"], strict=True):
        after["image_sha256"] = before["image_sha256"]
    assert rebound_payload == pinned  # Labels, provenance, author/time and geometry are unchanged.
    first = result.record.pages[0]
    assert first.reference_image_sha256 != first.rebound_image_sha256
    assert first.rgb8_sha256 == hashlib.sha256(expected_pixels).hexdigest()
    assert (first.pixel_width, first.pixel_height) == (600, 800)
    assert result.record.original_annotation_sha256 == artifact_digest(annotation)
    assert result.record.rebound_annotation_sha256 == artifact_digest(result.annotation)
    assert asdict(result.record)["label_changes"] == "none"
    with DocumentSource(
        FIXTURES / "original.tiff",
        asset_id=uuid4(),
        expected_sha256=annotation.original_sha256,
        mime_type="image/tiff",
    ) as source:
        for record in result.record.pages:
            rendered = source.render(record.page_number)
            assert record.rebound_image_sha256 == rendered.identity.image_sha256
            assert record.renderer_version == rendered.identity.renderer_version


def test_a_single_changed_pixel_rejects_even_when_reference_hash_is_repinned(inputs, tmp_path):
    path = tmp_path / "changed.png"
    with Image.open(FIXTURES / "page-1.png") as reference:
        reference.putpixel((0, 0), (254, 255, 255))
        reference.save(path)
    annotation = repin_page(inputs[1], path)
    with pytest.raises(AnnotationRenderBindingError):
        bind(annotation, paths={1: path, 2: FIXTURES / "page-2.png"})


def test_reference_byte_tampering_rejects_even_when_decoded_pixels_match(inputs, tmp_path):
    path = tmp_path / "changed-encoding.png"
    with Image.open(FIXTURES / "page-1.png") as reference:
        reference.save(path, compress_level=0)
    with pytest.raises(AnnotationRenderBindingError):
        bind(inputs[1], paths={1: path, 2: FIXTURES / "page-2.png"})


@pytest.mark.parametrize("keys", [(1,), (1, 2, 3)])
def test_every_annotated_page_requires_exact_reference_inventory(inputs, keys):
    with pytest.raises(AnnotationRenderBindingError):
        bind(inputs[1], paths={number: FIXTURES / "page-1.png" for number in keys})


def test_original_hash_and_reference_geometry_cannot_be_changed(inputs, tmp_path):
    path = tmp_path / "private-original"
    path.write_bytes(b"PRIVATE-ORIGINAL-DATA")
    with pytest.raises(AnnotationRenderBindingError) as failure:
        bind(inputs[1], original=path)
    assert "PRIVATE" not in str(failure.value)
    annotation = inputs[1]
    page = annotation.pages[0].model_copy(update={"pixel_width": 601})
    with pytest.raises(AnnotationRenderBindingError):
        bind(annotation.model_copy(update={"pages": (page, annotation.pages[1])}))


@pytest.mark.parametrize("change", ["alpha", "orientation", "profile"])
def test_ambiguous_display_transforms_are_not_silently_dropped(inputs, tmp_path, change):
    path = tmp_path / "display-transform.png"
    with Image.open(FIXTURES / "page-1.png") as reference:
        if change == "alpha":
            with reference.convert("RGBA") as rgba:
                rgba.save(path)
        elif change == "orientation":
            exif = Image.Exif()
            exif[274] = 6
            reference.save(path, exif=exif)
        else:
            reference.save(path, icc_profile=b"not-an-unprofiled-raster")
    with pytest.raises(AnnotationRenderBindingError):
        bind(repin_page(inputs[1], path), paths={1: path, 2: FIXTURES / "page-2.png"})


def test_reference_read_is_bounded_and_no_partial_annotation_is_returned(inputs, tmp_path):
    path = tmp_path / "oversized-reference.png"
    with path.open("wb") as reference:
        reference.write(b"\x89PNG\r\n\x1a\n")
        reference.truncate(100 * 1024 * 1024 + 1)
    pinned = artifact_digest(inputs[1])
    with pytest.raises(AnnotationRenderBindingError):
        bind(inputs[1], paths={1: FIXTURES / "page-1.png", 2: path})
    assert artifact_digest(inputs[1]) == pinned
