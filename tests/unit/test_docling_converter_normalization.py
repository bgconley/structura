from workers.docling.converter import _chunks_from_pages, _pages_from_docling


def test_pages_use_docling_text_item_provenance_when_page_text_is_absent() -> None:
    pages = _pages_from_docling(
        {
            "pages": {"1": {"page_no": 1, "size": {"width": 612, "height": 792}}},
            "texts": [
                {"text": "First paragraph", "prov": [{"page_no": 1}]},
                {"text": "Second paragraph", "prov": [{"page_no": 1}]},
            ],
        },
        fallback_text="fallback markdown",
    )

    assert len(pages) == 1
    assert pages[0].text == "First paragraph\nSecond paragraph"

    chunks = _chunks_from_pages(pages, fallback_markdown="fallback markdown")
    assert chunks[0].text == "First paragraph\nSecond paragraph"
