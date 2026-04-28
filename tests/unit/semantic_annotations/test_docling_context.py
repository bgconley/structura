from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.semantic_annotations.docling_context import build_docling_context


def test_build_docling_context_includes_grounding_ids_and_bounded_snippets() -> None:
    document_id = uuid4()
    page_id = uuid4()
    element_id = uuid4()
    table_id = uuid4()
    long_text = "invoice total due " * 200
    source = ExtractionSourceDocument(
        document_id=document_id,
        household_id=uuid4(),
        title="Invoice",
        original_filename="invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display="Acme",
        primary_folder_id=None,
        metadata={"phase8": {"quality": {"ocr_quality": "good"}}},
        pages=[
            ParsedPageText(
                page_id=page_id,
                page_number=1,
                text=long_text,
                image_asset_uri="file:///srv/structura/objects/derived/page.png",
                image_mime_type="image/png",
                image_sha256="a" * 64,
            )
        ],
        elements=[
            ParsedElementText(
                element_id=element_id,
                page_number=1,
                ordinal=3,
                text=long_text,
                bbox={"l": 1, "t": 2, "r": 3, "b": 4},
            )
        ],
        tables=[
            ParsedTableText(
                table_id=table_id,
                page_number=1,
                table_index=2,
                table_markdown="| total | $12.00 |",
                table_json={"rows": [["total", "$12.00"]]},
            )
        ],
    )

    context = build_docling_context(source)

    assert context["documentId"] == str(document_id)
    assert context["family"] == "invoice"
    assert context["pages"][0]["pageId"] == str(page_id)
    assert context["pages"][0]["imageSha256"] == "a" * 64
    assert "image_asset_uri" not in str(context)
    assert "file:///srv/structura" not in str(context)
    assert len(context["pages"][0]["textSnippet"]) <= 320
    assert context["pages"][0]["elements"][0]["elementId"] == str(element_id)
    assert context["pages"][0]["elements"][0]["bbox"] == {"l": 1, "t": 2, "r": 3, "b": 4}
    assert len(context["pages"][0]["elements"][0]["textSnippet"]) <= 240
    assert context["pages"][0]["tables"][0]["tableId"] == str(table_id)
    assert context["pages"][0]["tables"][0]["tableIndex"] == 2
