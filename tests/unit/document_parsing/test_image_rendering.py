from __future__ import annotations

import hashlib
import io
from importlib.metadata import version
from uuid import uuid4

import pytest
from PIL import Image, ImageDraw, features

from lib.document_parsing.source_adapter import DocumentSource, renderer_identity


def _render(path, mime_type="image/png"):
    original = path.read_bytes()
    asset_id = uuid4()
    with DocumentSource(
        path,
        asset_id=asset_id,
        expected_sha256=hashlib.sha256(original).hexdigest(),
        mime_type=mime_type,
    ) as source:
        inventory, rendered = source.inventory, source.render(1)
    assert path.read_bytes() == original
    assert inventory.original_asset_id == asset_id
    assert inventory.byte_size == len(original)
    assert rendered.identity.image_sha256 == hashlib.sha256(rendered.image_bytes).hexdigest()
    assert rendered.identity.page_number == inventory.pages[0].page_number == 1
    assert rendered.identity.native_text is None
    return inventory, rendered


def _draw_letter_t(image, ink):
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 5, 25, 8), fill=ink)
    draw.rectangle((14, 8, 17, 25), fill=ink)


@pytest.mark.parametrize("mode", ["RGBA", "LA"])
def test_transparent_black_text_remains_legible_on_white(tmp_path, mode):
    path = tmp_path / "transparent.png"
    background = (0, 0, 0, 0) if mode == "RGBA" else (0, 0)
    black = (0, 0, 0, 255) if mode == "RGBA" else (0, 255)
    translucent = (0, 0, 0, 128) if mode == "RGBA" else (0, 128)
    with Image.new(mode, (40, 30), background) as image:
        _draw_letter_t(image, black)
        image.putpixel((30, 20), translucent)
        image.save(path)
    inventory, rendered = _render(path)
    with Image.open(io.BytesIO(rendered.image_bytes)) as raster:
        assert raster.mode == "RGB" and raster.size == (40, 30)
        assert raster.getpixel((0, 0)) == (255, 255, 255)
        assert raster.getpixel((10, 6)) == raster.getpixel((15, 20)) == (0, 0, 0)
        assert raster.getpixel((30, 20)) == (127, 127, 127)
    assert (inventory.pages[0].width, inventory.pages[0].height) == (40, 30)
    assert rendered.identity.renderer_version.startswith("native-image-raster-white-v2/")


@pytest.mark.parametrize("transparency", [0, b"\x00\xff\x80"])
def test_palette_transparency_preserves_black_text_and_white_background(tmp_path, transparency):
    path = tmp_path / "palette.png"
    with Image.new("P", (40, 30), 0) as image:
        # Identical RGB values have different opacity; dropping the palette alpha
        # loses the entire letter even though the original displays legibly.
        image.putpalette([0, 0, 0] * 256)
        _draw_letter_t(image, 1)
        image.putpixel((30, 20), 2)
        image.save(path, transparency=transparency)
    _, rendered = _render(path)
    with Image.open(io.BytesIO(rendered.image_bytes)) as raster:
        assert raster.getpixel((0, 0)) == (255, 255, 255)
        assert raster.getpixel((10, 6)) == raster.getpixel((15, 20)) == (0, 0, 0)
        expected = (127, 127, 127) if isinstance(transparency, bytes) else (0, 0, 0)
        assert raster.getpixel((30, 20)) == expected


def test_alpha_composition_preserves_exif_orientation_and_page_geometry(tmp_path):
    path = tmp_path / "oriented.png"
    with Image.new("RGBA", (4, 2), (0, 0, 0, 0)) as image:
        image.putpixel((0, 0), (0, 0, 0, 255))
        exif = Image.Exif()
        exif[274] = 6
        image.save(path, exif=exif)
    inventory, rendered = _render(path)
    assert (inventory.pages[0].width, inventory.pages[0].height) == (2, 4)
    assert (rendered.identity.pixel_width, rendered.identity.pixel_height) == (2, 4)
    with Image.open(io.BytesIO(rendered.image_bytes)) as raster:
        assert raster.getpixel((1, 0)) == (0, 0, 0)
        assert raster.getpixel((0, 0)) == (255, 255, 255)
        assert raster.getexif().get(274) is None


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "P"])
def test_opaque_raster_pixels_and_inventory_are_preserved(tmp_path, mode):
    path = tmp_path / "opaque.png"
    with Image.new("RGB", (4, 2), (70, 120, 180)) as image:
        image.putpixel((0, 0), (10, 20, 30))
        expected = image.tobytes()
        with image.convert(mode, palette=Image.Palette.ADAPTIVE) as encoded:
            encoded.save(path)
    inventory, rendered = _render(path)
    assert inventory.mime_type == "image/png"
    assert (inventory.pages[0].width, inventory.pages[0].height) == (4, 2)
    with Image.open(io.BytesIO(rendered.image_bytes)) as raster:
        assert raster.tobytes() == expected


def test_renderer_identity_freezes_image_policy_and_png_compression_backend():
    encoder = f"Pillow-{version('Pillow')}/png-zlib-{features.version('zlib')}"
    assert renderer_identity("application/pdf") == (
        "pdfium",
        f"native-source-raster-v1/pypdfium2-{version('pypdfium2')}/{encoder}",
    )
    for mime_type in ("image/png", "image/jpeg", "image/tiff", "image/webp"):
        assert renderer_identity(mime_type) == (
            "pillow-exif-oriented",
            f"native-image-raster-white-v2/{encoder}",
        )


def test_compression_backend_change_invalidates_both_renderer_identities(monkeypatch):
    before = {mime: renderer_identity(mime) for mime in ("application/pdf", "image/png")}
    monkeypatch.setattr(features, "version", lambda feature: "another-png-backend")
    for mime, identity in before.items():
        assert renderer_identity(mime) != identity
