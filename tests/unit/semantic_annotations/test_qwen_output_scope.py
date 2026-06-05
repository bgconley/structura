from __future__ import annotations

import hashlib
from typing import Any, cast
from uuid import uuid4

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.semantic_annotations.qwen_output_scope import canonical_payload_filtered_to_source


def test_qwen_output_scope_filters_model_payload_to_requested_docling_pages() -> None:
    page_one = _page(1, "Invoice total $42")
    blank_page_two = _page(2, "")
    outside_page_id = uuid4()
    source = ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Two page invoice",
        original_filename="invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[page_one, blank_page_two],
        elements=[],
        tables=[],
    )

    normalized = canonical_payload_filtered_to_source(
        {
            "schema_name": "semantic_annotation_model_output",
            "schema_version": "v1",
            "document_type": "invoice",
            "pages": [
                {"page_id": str(outside_page_id), "page_number": 99},
                {"page_id": str(page_one.page_id), "page_number": 1},
            ],
            "regions": [
                {
                    "semantic_type": "billing_summary",
                    "grounding": {"kind": "page", "page_id": str(page_one.page_id)},
                },
                {
                    "semantic_type": "billing_summary",
                    "grounding": {"kind": "page", "page_id": str(outside_page_id)},
                },
            ],
            "quality_flags": {"needs_human_review": False},
        },
        source=source,
    )

    pages = cast(list[dict[str, Any]], normalized.payload["pages"])
    regions = cast(list[dict[str, Any]], normalized.payload["regions"])

    assert [page["page_id"] for page in pages] == [
        str(page_one.page_id),
        str(blank_page_two.page_id),
    ]
    assert pages[1]["document_type_hint"] == "no_extraction_target"
    assert regions == [
        {
            "semantic_type": "billing_summary",
            "grounding": {"kind": "page", "page_id": str(page_one.page_id)},
        }
    ]
    assert normalized.normalization == {
        "output_scope_filter_policy": "filter_to_requested_docling_pages",
        "out_of_window_pages_dropped": 1,
        "out_of_window_page_ids": [str(outside_page_id)],
        "out_of_window_regions_dropped": 1,
        "missing_blank_focus_pages_filled": 1,
        "missing_blank_focus_page_ids": [str(blank_page_two.page_id)],
        "missing_blank_focus_page_policy": "fill_no_extraction_target_page_only",
    }


def _page(page_number: int, text: str) -> ParsedPageText:
    image_bytes = f"page-{page_number}".encode()
    return ParsedPageText(
        page_id=uuid4(),
        page_number=page_number,
        text=text,
        image_bytes=image_bytes,
        image_mime_type="image/png",
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
    )
