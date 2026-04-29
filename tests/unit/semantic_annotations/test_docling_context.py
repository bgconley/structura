from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.semantic_annotations.docling_context import MAX_ELEMENTS_PER_PAGE, build_docling_context


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

    assert context["document"]["documentId"] == str(document_id)
    assert context["document"]["family"] == "invoice"
    assert context["focusPages"][0]["pageId"] == str(page_id)
    assert context["focusPages"][0]["imageSha256"] == "a" * 64
    assert "image_asset_uri" not in str(context)
    assert "file:///srv/structura" not in str(context)
    assert len(context["focusPages"][0]["textSnippet"]) <= 320
    assert context["focusPages"][0]["elements"][0]["elementId"] == str(element_id)
    assert context["focusPages"][0]["elements"][0]["bbox"] == {"l": 1, "t": 2, "r": 3, "b": 4}
    assert len(context["focusPages"][0]["elements"][0]["textSnippet"]) <= 240
    assert context["focusPages"][0]["tables"][0]["tableId"] == str(table_id)
    assert context["focusPages"][0]["tables"][0]["tableIndex"] == 2
    assert context["pages"] == context["focusPages"]

    model_context = build_docling_context(source, include_pages_alias=False)

    assert "focusPages" in model_context
    assert "pages" not in model_context


def test_build_docling_context_caps_element_context_per_page() -> None:
    page_id = uuid4()
    element_count = MAX_ELEMENTS_PER_PAGE + 5
    source = ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Dense service record",
        original_filename="service.pdf",
        mime_type="application/pdf",
        family="receipt",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=page_id,
                page_number=1,
                text="Dense service page",
                image_mime_type="image/png",
                image_sha256="b" * 64,
            )
        ],
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=1,
                ordinal=ordinal,
                text=f"service line {ordinal}",
                bbox=None,
            )
            for ordinal in range(1, element_count + 1)
        ],
        tables=[],
    )

    context = build_docling_context(source)

    page_context = context["pages"][0]
    assert page_context["elementCount"] == element_count
    assert page_context["elementsTruncated"] == 5
    assert len(page_context["elements"]) == MAX_ELEMENTS_PER_PAGE
    assert page_context["elements"][0]["ordinal"] == 1
    assert page_context["elements"][-1]["ordinal"] == MAX_ELEMENTS_PER_PAGE


def test_docling_context_keeps_document_outline_for_focus_page() -> None:
    source = _multi_page_source(
        page_texts=[
            "Seller Information Form Phenix Title",
            "Escrow Statement UWM mortgage escrow shortage",
            "Signature instructions",
        ]
    )

    context = build_docling_context(source, focus_page_numbers={2})

    assert context["document"]["pageCount"] == 3
    assert context["document"]["lexicalAnchors"] == [
        "escrow",
        "mortgage",
        "seller",
        "shortage",
        "title",
        "uwm",
    ]
    assert [page["pageNumber"] for page in context["document"]["pageOutline"]] == [1, 2, 3]
    assert [page["pageNumber"] for page in context["focusPages"]] == [2]
    assert "Seller Information" in context["document"]["pageOutline"][0]["textSnippet"]


def _multi_page_source(page_texts: list[str]) -> ExtractionSourceDocument:
    pages = [
        ParsedPageText(
            page_id=uuid4(),
            page_number=index,
            text=text,
            image_mime_type="image/png",
            image_sha256=f"{index:064d}"[-64:],
        )
        for index, text in enumerate(page_texts, start=1)
    ]
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Phase 8.5 Context Canary",
        original_filename="context.pdf",
        mime_type="application/pdf",
        family="generic",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=pages,
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=page.page_number,
                ordinal=1,
                text=page.text,
                bbox=None,
            )
            for page in pages
        ],
        tables=[],
    )
