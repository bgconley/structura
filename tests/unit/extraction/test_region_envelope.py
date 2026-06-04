from __future__ import annotations

from uuid import uuid4

from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.evidence_concretizer import attach_evidence_to_envelope, has_concrete_locator
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
)


def test_source_text_only_evidence_is_not_concrete() -> None:
    ref = EvidenceRef(
        document_id=str(uuid4()),
        source_engine="granite_vision_3b",
        source_text="Total $4.65",
    )

    assert has_concrete_locator(ref) is False


def test_semantic_region_and_page_number_is_concrete() -> None:
    ref = EvidenceRef(
        document_id=str(uuid4()),
        source_engine="granite_vision_3b",
        semantic_region_id=str(uuid4()),
        page_number=1,
        source_text="Total $4.65",
    )

    assert has_concrete_locator(ref) is True
    assert has_concrete_evidence([ref.model_dump(mode="json", exclude_none=True)]) is True


def test_structural_locator_evidence_requires_page_context() -> None:
    assert not has_concrete_evidence(
        [{"table_id": str(uuid4()), "row_index": 1, "source_engine": "granite_vision_3b"}]
    )
    assert not has_concrete_evidence(
        [{"element_id": str(uuid4()), "source_engine": "granite_vision_3b"}]
    )
    assert not has_concrete_evidence([{"bbox": [1, 2, 3, 4], "source_engine": "granite_vision_3b"}])

    assert has_concrete_evidence(
        [
            {
                "table_id": str(uuid4()),
                "row_index": 1,
                "page_number": 1,
                "source_engine": "granite_vision_3b",
            }
        ]
    )
    assert has_concrete_evidence(
        [
            {
                "element_id": str(uuid4()),
                "page_number": 1,
                "source_engine": "granite_vision_3b",
            }
        ]
    )
    assert has_concrete_evidence(
        [
            {
                "bbox": [1, 2, 3, 4],
                "page_number": 1,
                "source_engine": "granite_vision_3b",
            }
        ]
    )


def test_attach_evidence_to_envelope_uses_structura_context() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="receipt",
        semantic_type="receipt_payment_summary",
        target_schema="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        facts=[
            RegionFact(
                name="receipt.transaction.total",
                value={"amount": 4.65, "currency": "USD"},
                value_type="money",
            )
        ],
    )

    concretized = attach_evidence_to_envelope(
        envelope=envelope,
        ctx=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=annotation_id,
            semantic_region_id=region_id,
            page_number=1,
        ),
    )

    ref = concretized.facts[0].evidence[0]
    assert ref.document_id == str(document_id)
    assert ref.semantic_annotation_id == str(annotation_id)
    assert ref.semantic_region_id == str(region_id)
    assert ref.page_number == 1
    assert has_concrete_locator(ref) is True
