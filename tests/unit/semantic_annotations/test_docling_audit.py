from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.semantic_annotations.docling_audit import build_docling_audit, family_anchor_hits


def test_docling_audit_finds_real_estate_and_escrow_anchors() -> None:
    source = _source_with_pages(
        [
            "Phenix Title Seller Information Form seller proceeds wiring instructions",
            "UWM Final Escrow Statement escrow account shortage surplus",
        ]
    )

    audit = build_docling_audit(source)

    assert audit.page_count == 2
    assert "seller" in audit.lexical_anchors
    assert "escrow" in audit.lexical_anchors
    assert audit.anchor_counts["real_estate_title"] >= 2
    assert audit.anchor_counts["mortgage_escrow_statement"] >= 1
    assert audit.suggested_family_hints == (
        "real_estate_title",
        "mortgage_escrow_statement",
    )
    assert audit.family_tension == (
        "real_estate_title",
        "mortgage_escrow_statement",
    )


def test_docling_audit_finds_service_record_anchors_without_title_false_hint() -> None:
    source = _source_with_pages(
        [
            "MAX BMW Motorcycles R/O Open Date Mileage In VIN service labor invoice",
            "Parts part number tire service repair order amount paid",
        ]
    )

    audit = build_docling_audit(source)

    assert audit.anchor_counts["service_record"] >= 4
    assert "service_record" in audit.suggested_family_hints
    assert "real_estate_title" not in audit.suggested_family_hints
    assert "service" in audit.lexical_anchors
    assert "parts" in audit.lexical_anchors


def test_restaurant_receipt_does_not_trigger_financial_dispute_hint() -> None:
    source = _source_with_pages(
        [
            (
                "McDonald's receipt transaction subtotal tax total paid "
                "visa charge payment approval code"
            )
        ]
    )

    audit = build_docling_audit(source)

    assert audit.anchor_counts["receipt"] >= 2
    assert "receipt" in audit.suggested_family_hints
    assert "financial_dispute_form" not in audit.suggested_family_hints
    assert audit.family_tension == ()


def test_financial_dispute_hint_requires_dispute_trigger() -> None:
    source = _source_with_pages(
        [
            (
                "Cardholder dispute form unauthorized transaction charge "
                "merchant amount reason for dispute"
            )
        ]
    )

    audit = build_docling_audit(source)

    assert "financial_dispute_form" in audit.suggested_family_hints
    assert audit.anchor_counts["financial_dispute_form"] >= 3


def test_docling_audit_preserves_table_inventory() -> None:
    source = _source_with_pages(["BH Photo order subtotal tax paid"])

    audit = build_docling_audit(source)

    assert audit.table_count == 1
    assert audit.table_summaries[0].page_number == 1
    assert audit.table_summaries[0].has_table_json is True
    assert audit.table_summaries[0].table_signal == "strong"
    assert audit.table_summaries[0].weak_signal_reason is None
    assert "line" in audit.table_summaries[0].markdown_snippet


def test_family_anchor_hits_are_grouped_by_document_family() -> None:
    source = _source_with_pages(["Anthem claim denial patient responsibility"])

    hits = family_anchor_hits(source)

    assert hits["medical_eob"] == ("anthem", "claim", "denial", "patient_responsibility")
    assert "receipt" not in hits


def _source_with_pages(page_texts: list[str]) -> ExtractionSourceDocument:
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
        title="Phase 8.5 Canary",
        original_filename="canary.pdf",
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
        tables=[
            ParsedTableText(
                table_id=uuid4(),
                page_number=1,
                table_index=1,
                table_markdown="| line | amount |\n| tripod | $42.00 |",
                table_json={"rows": [["line", "amount"], ["tripod", "$42.00"]]},
            )
        ],
    )
