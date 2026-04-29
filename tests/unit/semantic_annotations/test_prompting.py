from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.semantic_annotations.prompting import build_semantic_planner_prompt


def test_semantic_planner_prompt_is_recall_oriented_without_canonical_facts() -> None:
    prompt = build_semantic_planner_prompt(_source())

    assert "semantic planner" in prompt
    assert "semantic planning, not extraction" in prompt
    assert "do not output field values" in prompt
    assert "canonical facts" in prompt
    assert "Emit all materially extractable regions" in prompt
    assert "First account for every input page image" in prompt
    assert "bounded recall is preferred over sparse omission" in prompt
    assert "Docling page_id, element_id, and table_id" in prompt
    assert "Emit document_type_candidates with competing family scores" in prompt
    assert "source_signal, coverage_role, extraction_scope" in prompt
    assert "Use planner_notes for routing warnings" in prompt
    assert "Return no more than 6 regions total" not in prompt
    assert "highest-value Granite routing targets" not in prompt
    assert "do not enumerate every visible field" not in prompt


def test_semantic_planner_prompt_includes_compact_hard_class_examples() -> None:
    prompt = build_semantic_planner_prompt(_source())

    assert "BMW service invoice" in prompt
    assert "BH retail order" in prompt
    assert "medical denial" in prompt
    assert "title seller information form" in prompt
    assert "escrow statement" in prompt
    assert "generic low-signal scan" in prompt
    assert "service_record_line_item_table" in prompt
    assert "receipt_payment_summary" in prompt
    assert "Vehicle or motorcycle repair orders" in prompt
    assert "route their service and parts rows as service_record_line_item_table" in prompt


def _source() -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="BMW service invoice",
        original_filename="bmw.pdf",
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
