from __future__ import annotations

from uuid import uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    envelope_from_normalization_projection,
)


def test_receipt_envelope_preserves_transaction_discount_total() -> None:
    document_id = str(uuid4())
    evidence = [
        {
            "document_id": document_id,
            "page_number": 1,
            "table_id": "receipt-summary",
            "row_index": 1,
            "source_engine": "granite_vision_3b",
        }
    ]

    envelope = envelope_from_normalization_projection(
        projection={
            "schema_name": "receipt",
            "schema_version": "v1",
            "document_id": document_id,
            "transaction": {
                "subtotal": {"amount": 20.0, "currency": "USD", "evidence": evidence},
                "tax": {"amount": 2.0, "currency": "USD", "evidence": evidence},
                "tip": {"amount": 3.0, "currency": "USD", "evidence": evidence},
                "discount_total": {"amount": 5.0, "currency": "USD", "evidence": evidence},
                "total": {"amount": 20.0, "currency": "USD", "evidence": evidence},
            },
        },
        model_output_schema_name="granite_receipt_payment_summary.v1",
        semantic_type="receipt_payment_summary",
        target_schema="receipt",
        resolved_document_type="receipt",
        source_engine="granite_vision_3b",
    )

    assert [(fact.name, fact.value) for fact in envelope.facts] == [
        ("receipt.transaction.subtotal", {"amount": 20.0, "currency": "USD", "evidence": evidence}),
        ("receipt.transaction.tax", {"amount": 2.0, "currency": "USD", "evidence": evidence}),
        ("receipt.transaction.tip", {"amount": 3.0, "currency": "USD", "evidence": evidence}),
        (
            "receipt.transaction.discount_total",
            {"amount": 5.0, "currency": "USD", "evidence": evidence},
        ),
        ("receipt.transaction.total", {"amount": 20.0, "currency": "USD", "evidence": evidence}),
    ]


def test_receipt_transaction_discount_total_claim_is_admissible() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="receipt-summary",
        row_index=1,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="receipt",
        semantic_type="receipt_payment_summary",
        target_schema="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        facts=[
            RegionFact(
                name="receipt.transaction.discount_total",
                value={"amount": 5.0, "currency": "USD"},
                value_type="money",
                evidence=[evidence],
            ),
        ],
    )

    claims = claims_from_region_envelope(envelope)

    assert [claim.canonical_key for claim in claims] == ["receipt.transaction.discount_total"]
    assert claims[0].typed_value == {"amount": 5.0, "currency": "USD"}
