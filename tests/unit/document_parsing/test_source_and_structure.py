from __future__ import annotations

import hashlib
import io
from uuid import uuid4

import pypdfium2 as pdfium
import pytest
from PIL import Image
from pydantic import ValidationError

from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.document_parsing.source_adapter import DocumentSource, DocumentSourceError
from lib.document_parsing.structure import DocumentStructure, SourceBox, SourceRender


def source_image(tmp_path):
    path = tmp_path / "synthetic.png"
    Image.new("RGB", (200, 100), "white").save(path)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_image_source_preserves_bytes_inventory_and_render_identity(tmp_path):
    path, digest = source_image(tmp_path)
    with DocumentSource(
        path, asset_id=uuid4(), expected_sha256=digest, mime_type="image/png"
    ) as source:
        assert len(source.inventory.pages) == 1
        rendered = source.render(1)
        assert rendered.identity.pixel_width == 200
        assert rendered.identity.pixel_height == 100
        assert rendered.identity.image_sha256 == hashlib.sha256(rendered.image_bytes).hexdigest()
        assert rendered.identity.native_text is None
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        with pytest.raises(DocumentSourceError):
            source.render(2)
        with pytest.raises(DocumentSourceError):
            source.render(1, max_pixels=100)
    with pytest.raises(DocumentSourceError, match="hash"):
        DocumentSource(path, asset_id=uuid4(), expected_sha256="0" * 64, mime_type="image/png")


def test_pdf_inventory_is_complete_before_render_budget_and_includes_rotation(tmp_path):
    path = tmp_path / "two-pages.pdf"
    pdf = pdfium.PdfDocument.new()
    first = pdf.new_page(300, 400)
    first.close()
    second = pdf.new_page(600, 800)
    second.set_rotation(90)
    second.close()
    pdf.save(path)
    pdf.close()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with DocumentSource(
        path, asset_id=uuid4(), expected_sha256=digest, mime_type="application/pdf"
    ) as source:
        assert [page.page_number for page in source.inventory.pages] == [1, 2]
        assert source.inventory.pages[1].rotation_degrees == 90
        render = source.render(2, scale=1)
        assert (render.identity.pixel_width, render.identity.pixel_height) == (800, 600)
        assert render.identity.native_text == ""
        assert render.identity.native_text_origin == "pdf_native"
    with pytest.raises(DocumentSourceError, match="page count"):
        DocumentSource(
            path, asset_id=uuid4(), expected_sha256=digest, mime_type="application/pdf", max_pages=1
        )


def test_multipage_image_is_not_silently_treated_as_one_page(tmp_path):
    path = tmp_path / "two-pages.tiff"
    a, b = Image.new("RGB", (20, 30), "red"), Image.new("RGB", (40, 50), "blue")
    a.save(path, save_all=True, append_images=[b])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with DocumentSource(
        path, asset_id=uuid4(), expected_sha256=digest, mime_type="image/tiff"
    ) as source:
        assert len(source.inventory.pages) == 2
        page = source.render(2)
        with Image.open(io.BytesIO(page.image_bytes)) as image:
            assert image.size == (40, 50)
            assert image.getpixel((0, 0)) == (0, 0, 255)


def model_output():
    return {
        "page_number": 1,
        "state": "processed",
        "diagnostics": [],
        "elements": [
            {
                "kind": "paragraph",
                "text": "Invoice A-123",
                "bbox": {"left": 100, "top": 100, "right": 900, "bottom": 500},
                "parent_index": None,
                "table": None,
            }
        ],
    }


def test_structure_ids_replay_stably_and_model_text_does_not_gain_native_authority():
    render = SourceRender(
        page_number=1,
        image_sha256="a" * 64,
        pixel_width=200,
        pixel_height=100,
        renderer="pdfium",
        renderer_version="test",
        native_text="Invoice A-123",
        native_text_origin="pdf_native",
    )
    generation = uuid4()
    output = PageParseOutput.model_validate(model_output())
    a = normalize_page(output, render, generation)
    b = normalize_page(output, render, generation)
    c = normalize_page(output, render, uuid4())
    assert a == b and a.id != c.id and a.elements[0].id != c.elements[0].id
    assert a.elements[0].text_origin == "model_transcription"
    assert a.elements[0].bbox == SourceBox(left=20, top=10, right=180, bottom=50)
    invalid = model_output()
    invalid["page_number"] = 2
    with pytest.raises(ValueError, match="page reference"):
        normalize_page(PageParseOutput.model_validate(invalid), render, generation)
    invalid = model_output()
    invalid["elements"][0]["parent_index"] = 0
    with pytest.raises(ValueError, match="earlier"):
        normalize_page(PageParseOutput.model_validate(invalid), render, generation)


def test_generation_cannot_omit_source_pages_or_fake_invocation(tmp_path):
    path, digest = source_image(tmp_path)
    generation = uuid4()
    with DocumentSource(
        path, asset_id=uuid4(), expected_sha256=digest, mime_type="image/png"
    ) as source:
        with pytest.raises(ValidationError, match="Every source page"):
            DocumentStructure(
                parse_generation_id=generation,
                processing_run_id=uuid4(),
                source=source.inventory,
                pages=(),
                invocations=(),
            )
        page = normalize_page(
            PageParseOutput.model_validate(model_output()), source.render(1).identity, generation
        )
        with pytest.raises(ValidationError, match="invocation provenance"):
            DocumentStructure(
                parse_generation_id=generation,
                processing_run_id=uuid4(),
                source=source.inventory,
                pages=(page,),
                invocations=(),
            )


@pytest.mark.parametrize("right", [-1, 0, float("nan"), float("inf")])
def test_invalid_source_geometry_is_rejected(right):
    with pytest.raises(ValidationError):
        SourceBox(left=0, top=0, right=right, bottom=20)
