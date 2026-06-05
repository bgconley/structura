from __future__ import annotations

from uuid import uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.region_envelope import EvidenceRef, RegionExtractionEnvelope, RegionFact


def test_claims_require_structural_anchor() -> None:
    document_id = uuid4()
    anchored_region_id = uuid4()
    unanchored_region_id = uuid4()
    anchored = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(anchored_region_id),
        resolved_document_type="invoice",
        semantic_type="payment_summary",
        target_schema="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        facts=[
            RegionFact(
                name="invoice.total_amount",
                value={"amount": 42.5, "currency": "USD"},
                value_type="money",
                evidence=[
                    EvidenceRef(
                        document_id=str(document_id),
                        semantic_region_id=str(anchored_region_id),
                        page_number=1,
                        table_id="table-1",
                        row_index=3,
                        source_engine="granite_vision_3b",
                    )
                ],
            )
        ],
    )
    unanchored = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(unanchored_region_id),
        resolved_document_type="invoice",
        semantic_type="payment_summary",
        target_schema="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        facts=[
            RegionFact(
                name="invoice.tax_total",
                value={"amount": 2.5, "currency": "USD"},
                value_type="money",
                evidence=[
                    EvidenceRef(
                        document_id=str(document_id),
                        semantic_region_id=str(unanchored_region_id),
                        source_engine="granite_vision_3b",
                        source_text="Tax $2.50",
                    )
                ],
            )
        ],
    )

    assert [claim.canonical_key for claim in claims_from_region_envelope(anchored)] == [
        "invoice.total_amount"
    ]
    assert claims_from_region_envelope(unanchored) == []


def test_claim_id_ignores_raw_source_payload_noise() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="table-1",
        row_index=3,
        source_engine="granite_vision_3b",
    )

    def envelope(raw_noise: str) -> RegionExtractionEnvelope:
        return RegionExtractionEnvelope(
            document_id=str(document_id),
            semantic_region_id=str(region_id),
            resolved_document_type="invoice",
            semantic_type="payment_summary",
            target_schema="invoice",
            model_output_schema_name="granite_payment_summary.v1",
            facts=[
                RegionFact(
                    name="invoice.total_amount",
                    value={"amount": 42.5, "currency": "USD"},
                    value_type="money",
                    evidence=[evidence],
                    source_payload={"raw_model_text": raw_noise},
                )
            ],
        )

    first = claims_from_region_envelope(envelope("first stochastic phrasing"))[0]
    second = claims_from_region_envelope(envelope("second stochastic phrasing"))[0]

    assert first.claim_id == second.claim_id
    assert first.typed_value == {"amount": 42.5, "currency": "USD"}
    assert first.source_engine == "granite"
