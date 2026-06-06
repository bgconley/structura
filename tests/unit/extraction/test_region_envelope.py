from __future__ import annotations

from uuid import uuid4

from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.evidence_concretizer import attach_evidence_to_envelope, has_concrete_locator
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    envelope_from_normalization_projection,
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


def test_medical_eob_envelope_preserves_allowed_and_paid_line_amounts() -> None:
    document_id = str(uuid4())
    envelope = envelope_from_normalization_projection(
        projection={
            "schema_name": "medical_eob",
            "schema_version": "v1",
            "document_id": document_id,
            "service_lines": [
                {
                    "service_description": "Office visit",
                    "billed_amount": {"amount": 120.0, "currency": "USD"},
                    "allowed_amount": {"amount": 80.0, "currency": "USD"},
                    "paid_amount": {"amount": 50.0, "currency": "USD"},
                    "patient_responsibility": {"amount": 30.0, "currency": "USD"},
                    "evidence": [
                        {
                            "document_id": document_id,
                            "page_number": 2,
                            "table_id": "eob-table",
                            "row_index": 4,
                            "source_engine": "granite_vision_3b",
                        }
                    ],
                }
            ],
        },
        model_output_schema_name="granite_medical_service_lines.v1",
        semantic_type="covered_services_line_item_table",
        target_schema="medical_eob",
        resolved_document_type="medical_eob",
        source_engine="granite_vision_3b",
    )

    line_item = envelope.line_items[0]
    assert line_item.gross_amount == 120.0
    assert line_item.allowed_amount == 80.0
    assert line_item.plan_paid_amount == 50.0
    assert line_item.net_amount == 30.0
    assert line_item.currency_code == "USD"


def test_invoice_envelope_preserves_shipping_and_discount_totals() -> None:
    document_id = str(uuid4())
    evidence = [
        {
            "document_id": document_id,
            "page_number": 1,
            "table_id": "invoice-totals",
            "row_index": 1,
            "source_engine": "granite_vision_3b",
        }
    ]

    envelope = envelope_from_normalization_projection(
        projection={
            "schema_name": "invoice",
            "schema_version": "v1",
            "document_id": document_id,
            "totals": {
                "subtotal": {"amount": 100.0, "currency": "USD", "evidence": evidence},
                "tax_total": {"amount": 10.0, "currency": "USD", "evidence": evidence},
                "shipping_total": {"amount": 5.0, "currency": "USD", "evidence": evidence},
                "discount_total": {"amount": 15.0, "currency": "USD", "evidence": evidence},
                "total": {"amount": 100.0, "currency": "USD", "evidence": evidence},
            },
        },
        model_output_schema_name="granite_invoice_line_items.v1",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        resolved_document_type="invoice",
        source_engine="granite_vision_3b",
    )

    assert [(fact.name, fact.value) for fact in envelope.facts] == [
        ("invoice.subtotal", {"amount": 100.0, "currency": "USD", "evidence": evidence}),
        ("invoice.tax_total", {"amount": 10.0, "currency": "USD", "evidence": evidence}),
        ("invoice.shipping_total", {"amount": 5.0, "currency": "USD", "evidence": evidence}),
        ("invoice.discount_total", {"amount": 15.0, "currency": "USD", "evidence": evidence}),
        ("invoice.total_amount", {"amount": 100.0, "currency": "USD", "evidence": evidence}),
    ]
