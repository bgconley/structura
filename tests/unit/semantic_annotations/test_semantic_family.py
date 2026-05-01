from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
)
from lib.semantic_annotations.semantic_family import semantic_document_family_decision


def test_semantic_family_reconciles_title_anchors_over_phase4_receipt() -> None:
    source = _source(
        family="receipt",
        title="Phenix Title Seller Info",
        text=(
            "Seller Information Form seller proceeds title company closing "
            "settlement wiring instructions"
        ),
    )
    decision = semantic_document_family_decision(
        source,
        _manifest(source, document_type="receipt"),
    )

    assert decision.family == "real_estate_title"
    assert decision.should_update is True
    assert decision.reason == "docling_anchor_family_supersedes_phase4"


def test_semantic_family_keeps_qwen_service_record_when_docling_supports_it() -> None:
    source = _source(
        family="invoice",
        title="BMW CE-04 run in service",
        text="Repair order service labor parts VIN mileage motorcycle payment",
    )
    decision = semantic_document_family_decision(
        source,
        _manifest(source, document_type="service_record"),
    )

    assert decision.family == "service_record"
    assert decision.should_update is True
    assert decision.reason == "semantic_document_type_with_docling_support"


def test_semantic_family_does_not_blindly_replace_supported_phase4_family() -> None:
    source = _source(
        family="invoice",
        title="Plain invoice",
        text="Invoice number bill to balance due",
    )
    decision = semantic_document_family_decision(
        source,
        _manifest(source, document_type="medical_eob"),
    )

    assert decision.family == "invoice"
    assert decision.should_update is False
    assert decision.reason == "retain_existing_family"


def test_semantic_generic_downgrades_unsupported_phase4_invoice_family() -> None:
    source = _source(
        family="invoice",
        title="Scan Oct 8",
        text="Small scanned table with handwritten rows and no business identifiers",
    )
    decision = semantic_document_family_decision(
        source,
        _manifest(source, document_type="generic_form"),
    )

    assert decision.family == "generic"
    assert decision.should_update is True
    assert decision.reason == "semantic_generic_downgrades_unsupported_phase4_family"


def test_semantic_generic_keeps_supported_phase4_invoice_family() -> None:
    source = _source(
        family="invoice",
        title="Plain invoice",
        text="Invoice number bill to balance due",
    )
    decision = semantic_document_family_decision(
        source,
        _manifest(source, document_type="generic_form"),
    )

    assert decision.family == "invoice"
    assert decision.should_update is False
    assert decision.reason == "retain_existing_family"


def _source(*, family: str, title: str, text: str) -> ExtractionSourceDocument:
    page_id = uuid4()
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title=title,
        original_filename=f"{title}.pdf",
        mime_type="application/pdf",
        family=family,
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={"phase4": {"classification": {"family": family}}},
        pages=[
            ParsedPageText(
                page_id=page_id,
                page_number=1,
                text=text,
                image_bytes=b"page",
                image_mime_type="image/png",
                image_sha256=None,
            )
        ],
        elements=[],
        tables=[],
    )


def _manifest(source: ExtractionSourceDocument, *, document_type: str) -> DocumentSemanticManifest:
    page = source.pages[0]
    return DocumentSemanticManifest(
        document_id=source.document_id,
        household_id=source.household_id,
        quality_mode="smart",
        profile_name="qwen3-vl-8b-fp8-semantic:v1",
        source_engine="qwen3_vl_8b",
        model_name="Qwen/Qwen3-VL-8B-Instruct-FP8",
        model_version="v1",
        prompt_version="phase8_5-semantic-smart-v3",
        pages=[
            PageSemanticAnnotation(
                page_id=page.page_id,
                page_number=page.page_number,
                page_role="semantic_page",
                document_type_hint=document_type,
                confidence=0.9,
            )
        ],
        regions=[],
        confidence={"overall": 0.9},
        manifest={"document_type": document_type},
        input_page_hashes=(),
    )
