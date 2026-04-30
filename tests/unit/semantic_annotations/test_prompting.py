from __future__ import annotations

import json
from uuid import uuid4

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.semantic_annotations.prompting import build_semantic_planner_prompt


def test_semantic_planner_prompt_is_recall_oriented_without_canonical_facts() -> None:
    prompt = build_semantic_planner_prompt(_source())

    assert "semantic document-understanding layer" in prompt
    assert "semantic inventory and extraction intent, not canonical extraction" in prompt
    assert "do not output field values" in prompt
    assert "canonical facts" in prompt
    assert "Emit all materially extractable regions" in prompt
    assert "First inventory every input page image" in prompt
    assert "Inspect layout, table structure, visual grouping" in prompt
    assert "full-page, table, element, or crop context" in prompt
    assert "bounded recall is preferred over sparse omission" in prompt
    assert "Docling page_id, element_id, and table_id" in prompt
    assert "Emit document_type_candidates with competing family scores" in prompt
    assert "source_signal, coverage_role, extraction_scope" in prompt
    assert "Use planner_notes for routing warnings" in prompt
    assert "Return no more than 6 regions total" not in prompt
    assert "highest-value Granite routing targets" not in prompt
    assert "do not enumerate every visible field" not in prompt


def test_semantic_planner_prompt_marks_full_outline_as_context_only_for_focus_pages() -> None:
    source = _source()
    prompt = build_semantic_planner_prompt(source, focus_page_numbers={1})

    assert "document.pageOutline is context-only" in prompt
    assert "pages[] must contain exactly the focusPages/input image pages" in prompt
    context = json.loads(prompt.split("Docling context: ", 1)[1])
    assert context["document"]["focusPageContract"] == {
        "allowedPageIds": [str(source.pages[0].page_id)],
        "allowedPageNumbers": [1],
        "pagesArrayMustMatchFocusPages": True,
        "pageOutlineIsContextOnly": True,
    }


def test_semantic_planner_prompt_includes_compact_class_examples_not_private_docs() -> None:
    prompt = build_semantic_planner_prompt(_source())

    assert "vehicle_service_invoice" in prompt
    assert "retail_order" in prompt
    assert "medical_denial" in prompt
    assert "title_seller_information_form" in prompt
    assert "escrow_statement" in prompt
    assert "generic_low_signal_form" in prompt
    assert "service_record_line_item_table" in prompt
    assert "receipt_payment_summary" in prompt
    assert "continuation_group" in prompt
    assert "requires_full_page_image" in prompt
    assert "BMW service invoice" not in prompt
    assert "BH retail order" not in prompt
    assert "Vehicle or motorcycle repair orders" not in prompt
    assert "Every service_record_line_item_table" not in prompt
    assert "continuation_group=service_lines" not in prompt
    assert "requires_full_page_image=true" not in prompt


def _source() -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Representative vehicle service invoice",
        original_filename="vehicle-service.pdf",
        mime_type="application/pdf",
        family="service_record",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=uuid4(),
                page_number=1,
                text="Service invoice line items and payment summary",
                image_mime_type="image/png",
                image_sha256="a" * 64,
            )
        ],
        elements=[],
        tables=[],
    )
