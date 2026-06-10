from __future__ import annotations

from uuid import uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.docling_anchor_resolution import resolve_docling_anchors_for_envelope
from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
)
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
)


def _source(document_id, element_text: str, page_text: str) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=uuid4(),
        title="Escrow statement",
        original_filename="escrow.pdf",
        mime_type="application/pdf",
        family="mortgage_escrow_statement",
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[ParsedPageText(page_id=uuid4(), page_number=1, text=page_text)],
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=1,
                ordinal=1,
                text=element_text,
                bbox=[10.0, 20.0, 220.0, 40.0],
            )
        ],
        tables=[],
    )


def _page_only_envelope(document_id, region_id) -> RegionExtractionEnvelope:
    return RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="document_observation",
        semantic_type="escrow_summary",
        target_schema="document_observation",
        model_output_schema_name="granite_mortgage_escrow_statement.v1",
        observations=[
            RegionFact(
                name="loan_number",
                value="0176595130",
                value_type="string",
                source_text="0176595130",
                evidence=[
                    EvidenceRef(
                        document_id=str(document_id),
                        semantic_region_id=str(region_id),
                        page_number=1,
                        page_id=str(uuid4()),
                        source_text="0176595130",
                        source_engine="granite_vision_3b",
                    )
                ],
            )
        ],
    )


def test_page_only_evidence_upgrades_to_docling_element_anchor() -> None:
    document_id = uuid4()
    envelope = _page_only_envelope(document_id, uuid4())
    source = _source(document_id, "Loan Number: 0176595130", "Loan Number: 0176595130\nEscrow")

    resolved, count = resolve_docling_anchors_for_envelope(envelope, source)

    assert count == 1
    ref = resolved.observations[0].evidence[0]
    assert ref.element_id is not None
    assert ref.bbox == [10.0, 20.0, 220.0, 40.0]
    # The anchored value can now become a Claim.
    claims = claims_from_region_envelope(resolved)
    assert [claim.canonical_key for claim in claims] == ["loan_number"]


def test_page_only_evidence_falls_back_to_page_text_span() -> None:
    document_id = uuid4()
    envelope = _page_only_envelope(document_id, uuid4())
    source = _source(document_id, "Unrelated element", "Header\nLoan 0176595130 active")

    resolved, count = resolve_docling_anchors_for_envelope(envelope, source)

    assert count == 1
    ref = resolved.observations[0].evidence[0]
    assert ref.element_id is None
    assert ref.text_span == {"start": 12, "end": 22, "basis": "page_text"}


def test_unmatched_page_only_evidence_stays_unanchored() -> None:
    document_id = uuid4()
    envelope = _page_only_envelope(document_id, uuid4())
    source = _source(document_id, "Totally different", "Nothing matching here")

    resolved, count = resolve_docling_anchors_for_envelope(envelope, source)

    assert count == 0
    ref = resolved.observations[0].evidence[0]
    assert ref.element_id is None and ref.bbox is None and ref.text_span is None
    assert claims_from_region_envelope(resolved) == []


def test_structural_evidence_is_left_untouched() -> None:
    document_id = uuid4()
    region_id = uuid4()
    envelope = _page_only_envelope(document_id, region_id)
    anchored_ref = (
        envelope.observations[0].evidence[0].model_copy(update={"table_id": "t-1", "row_index": 2})
    )
    envelope.observations[0].evidence = [anchored_ref]
    source = _source(document_id, "Loan Number: 0176595130", "Loan Number: 0176595130")

    resolved, count = resolve_docling_anchors_for_envelope(envelope, source)

    assert count == 0
    assert resolved.observations[0].evidence[0].table_id == "t-1"
