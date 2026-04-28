from __future__ import annotations

from types import SimpleNamespace

from lib.storage import ObjectStorage
from workers.previews import service as preview_service


def test_page_preview_uses_pdfium_png_when_available(monkeypatch, tmp_path) -> None:
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    original = storage.store_bytes(b"%PDF-1.7\n%%EOF\n", kind="canonical", role="original")

    class FakeImage:
        mode = "RGB"

        def save(self, output, *, format: str) -> None:
            assert format == "PNG"
            output.write(b"\x89PNG\r\n\x1a\nrendered")

    class FakeBitmap:
        def to_pil(self) -> FakeImage:
            return FakeImage()

    class FakePage:
        def render(self, *, scale: int) -> FakeBitmap:
            assert scale == 2
            return FakeBitmap()

        def close(self) -> None:
            pass

    class FakePdf:
        def __init__(self, path: str) -> None:
            assert path.endswith("original.blob")

        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: int) -> FakePage:
            assert index == 0
            return FakePage()

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        preview_service,
        "import_module",
        lambda name: SimpleNamespace(PdfDocument=FakePdf),
    )

    image = preview_service._page_preview_image(
        storage,
        {
            "mime_type": "application/pdf",
            "original_asset_uri": original.uri,
        },
        {"page_number": 1},
    )

    assert image.mime_type == "image/png"
    assert image.preview_kind == "pdf_raster_page_image"
    assert image.data.startswith(b"\x89PNG")
