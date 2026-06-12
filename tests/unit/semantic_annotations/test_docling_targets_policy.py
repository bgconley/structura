from __future__ import annotations

import inspect
from datetime import date
from uuid import uuid4

from lib.extraction.models import ExtractionSourceDocument, ParsedElementText, ParsedPageText
from lib.semantic_annotations import docling_targets as docling_targets_module
from lib.semantic_annotations.docling_targets import (
    augment_manifest_with_docling_structural_targets,
)
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)


def test_docling_structural_target_priority_uses_explicit_semantic_type_registry() -> None:
    source = inspect.getsource(docling_targets_module)

    assert "semantic_type.endswith" not in source
    assert "LINE_ITEM_TABLE_SEMANTIC_TYPES" in source


def _source_with_pages(
    *,
    family: str,
    title: str,
    page_texts: list[str],
) -> ExtractionSourceDocument:
    pages = [
        ParsedPageText(
            page_id=uuid4(),
            page_number=index,
            text=text,
            has_text_layer=True,
        )
        for index, text in enumerate(page_texts, start=1)
    ]
    elements = [
        ParsedElementText(
            element_id=uuid4(),
            page_number=page.page_number,
            ordinal=page.page_number,
            text=page.text,
        )
        for page in pages
    ]
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title=title,
        original_filename=f"{title}.pdf",
        mime_type="application/pdf",
        family=family,
        subtype=None,
        sensitivity="standard",
        document_date=date(2026, 6, 1),
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=pages,
        elements=elements,
        tables=[],
    )


def _manifest_with_region(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> DocumentSemanticManifest:
    pages = [
        PageSemanticAnnotation(
            page_id=page.page_id,
            page_number=page.page_number,
            page_role="content",
            extraction_usefulness="unknown",
        )
        for page in source.pages
    ]
    return DocumentSemanticManifest(
        document_id=source.document_id,
        household_id=source.household_id,
        quality_mode="smart",
        profile_name="qwen",
        source_engine="qwen3_vl_8b",
        model_name="qwen",
        model_version="t",
        prompt_version="t",
        pages=pages,
        regions=[region],
        confidence={},
        manifest={"pages": [], "regions": []},
    )


def test_qwen_observation_on_wrong_page_does_not_suppress_docling_escrow_target() -> None:
    source = _source_with_pages(
        family="mortgage_escrow_statement",
        title="UWM Final Escrow Statement",
        page_texts=[
            "Cover page with general servicing notes.",
            "Escrow mortgage shortage surplus details and monthly payment.",
        ],
    )
    qwen_region = SemanticRegionAnnotation(
        semantic_type="escrow_summary",
        priority="high",
        granite_task="kvp",
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        target_schema="document_observation",
        expected_fields=("loan_number", "monthly_payment"),
    )

    augmented = augment_manifest_with_docling_structural_targets(
        source,
        _manifest_with_region(source, qwen_region),
    )

    escrow_regions = [
        region for region in augmented.regions if region.semantic_type == "escrow_summary"
    ]
    assert len(escrow_regions) == 2
    assert {region.grounding.page_id for region in escrow_regions} == {
        source.pages[0].page_id,
        source.pages[1].page_id,
    }


def test_qwen_observation_on_same_page_suppresses_duplicate_docling_target() -> None:
    source = _source_with_pages(
        family="mortgage_escrow_statement",
        title="UWM Final Escrow Statement",
        page_texts=[
            "Cover page with general servicing notes.",
            "Escrow mortgage shortage surplus details and monthly payment.",
        ],
    )
    qwen_region = SemanticRegionAnnotation(
        semantic_type="escrow_summary",
        priority="high",
        granite_task="kvp",
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[1].page_id),
        target_schema="document_observation",
        expected_fields=(
            "loan_number",
            "escrow_shortage",
            "escrow_surplus",
            "monthly_payment",
        ),
    )

    augmented = augment_manifest_with_docling_structural_targets(
        source,
        _manifest_with_region(source, qwen_region),
    )

    escrow_regions = [
        region for region in augmented.regions if region.semantic_type == "escrow_summary"
    ]
    assert escrow_regions == [qwen_region]
