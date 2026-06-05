from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.semantic_annotations.manifest_merge import merge_partial_manifests, resolve_document_type
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)


def test_merge_prefers_docling_anchored_document_type_over_first_chunk() -> None:
    source = _source(
        family="unknown",
        texts=[
            "Payment coupon and account summary",
            "UWM escrow shortage statement and mortgage escrow analysis",
        ],
    )
    partials = [
        _partial(source, page_index=0, document_type="receipt", page_hint="receipt"),
        _partial(
            source,
            page_index=1,
            document_type="mortgage_escrow_statement",
            page_hint="mortgage_escrow_statement",
        ),
    ]

    merged = merge_partial_manifests(
        source,
        partials,
        quality_mode="smart",
        profile_name="qwen3-vl-8b-fp8-semantic:v1",
        prompt_version="phase8_5-semantic-smart-v3",
    )

    assert merged.manifest["document_type"] == "mortgage_escrow_statement"
    resolution = merged.confidence["document_type_resolution"]
    assert resolution["reason"] == "top_weighted_vote"
    assert resolution["docling_anchor_hints"] == ["mortgage_escrow_statement"]


def test_merge_downgrades_conflicting_unanchored_page_votes_to_generic_form() -> None:
    source = _source(
        family="unknown",
        texts=["Cover page", "Form details"],
    )
    partials = [
        _partial(source, page_index=0, document_type="invoice", page_hint="invoice"),
        _partial(source, page_index=1, document_type="medical_eob", page_hint="medical_eob"),
    ]

    resolution = resolve_document_type(source, partials)

    assert resolution.selected == "generic_form"
    assert resolution.reason == "conflicting_unanchored_page_votes"
    assert resolution.page_votes == {"invoice": 0.9, "medical_eob": 0.9}


def _source(*, family: str, texts: list[str]) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Private canary document",
        original_filename="canary.pdf",
        mime_type="application/pdf",
        family=family,
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=uuid4(),
                page_number=index + 1,
                text=text,
                image_bytes=b"page",
                image_mime_type="image/png",
                image_sha256=None,
            )
            for index, text in enumerate(texts)
        ],
        elements=[],
        tables=[],
    )


def _partial(
    source: ExtractionSourceDocument,
    *,
    page_index: int,
    document_type: str,
    page_hint: str,
) -> DocumentSemanticManifest:
    page = source.pages[page_index]
    region = SemanticRegionAnnotation(
        semantic_type="generic_form_kvp",
        priority="medium",
        granite_task="kvp",
        target_schema="document_observation",
        grounding=SemanticGroundingRef(kind="page", page_id=page.page_id),
        expected_fields=("visible_fields",),
        confidence=0.8,
    )
    return DocumentSemanticManifest(
        document_id=source.document_id,
        household_id=source.household_id,
        quality_mode="smart",
        profile_name="qwen3-vl-8b-fp8-semantic:v1",
        source_engine="qwen3_vl_8b",
        model_name="Qwen/Qwen3-VL-8B-Instruct-FP8",
        model_version="test",
        prompt_version="phase8_5-semantic-smart-v3",
        pages=[
            PageSemanticAnnotation(
                page_id=page.page_id,
                page_number=page.page_number,
                page_role="form_page",
                document_type_hint=page_hint,
                confidence=0.9,
            )
        ],
        regions=[region],
        confidence={"overall": 0.8},
        manifest={
            "schema_name": "semantic_annotation_manifest",
            "schema_version": "v1",
            "document_type": document_type,
            "quality_flags": {"needs_human_review": False, "visual_degradation": False},
        },
        input_page_hashes=(),
    )
