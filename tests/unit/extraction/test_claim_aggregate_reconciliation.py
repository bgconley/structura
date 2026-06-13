from __future__ import annotations

from uuid import uuid4

from lib.extraction.claim_aggregate_reconciliation import (
    resolve_claim_regions_for_family,
)
from lib.extraction.claims import Claim, ClaimAnchor
from lib.extraction.region_reconciliation import RegionExtraction


def test_claim_region_projection_derives_source_family_from_claims_not_raw_payload() -> None:
    document_id = uuid4()
    region_id = uuid4()

    projection = resolve_claim_regions_for_family(
        family="medical_eob",
        missing_claims_reason="claims_required_for_medical_eob_aggregate",
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=region_id,
                semantic_type="covered_services_line_item_table",
                claims=(
                    Claim(
                        claim_id="claim-medical-payer",
                        document_id=str(document_id),
                        source_engine="granite",
                        anchor=ClaimAnchor(
                            page_number=1,
                            semantic_region_id=str(region_id),
                        ),
                        canonical_key="medical_eob.payer.display_name",
                        raw_value="Anthem Blue Cross",
                        typed_value="Anthem Blue Cross",
                        value_type="text",
                        confidence=0.91,
                        method="granite_medical_service_lines.v1",
                    ),
                ),
            )
        ],
    )

    assert projection is not None
    assert projection.claim_projection.fields["payer"]["display_name"] == "Anthem Blue Cross"
    assert projection.metadata["source_families"] == ["medical_eob"]
    assert "invoice" not in projection.metadata["source_families"]


def test_claim_region_projection_records_unclaimed_regions_with_family_reason() -> None:
    document_id = uuid4()
    unclaimed_extraction_id = uuid4()
    unclaimed_region_id = uuid4()
    claimed_region_id = uuid4()

    projection = resolve_claim_regions_for_family(
        family="document_observation",
        missing_claims_reason="claims_required_for_document_observation_aggregate",
        regions=[
            RegionExtraction(
                extraction_id=unclaimed_extraction_id,
                semantic_region_id=unclaimed_region_id,
                semantic_type="generic_form_kvp",
            ),
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=claimed_region_id,
                semantic_type="generic_form_kvp",
                claims=(
                    Claim(
                        claim_id="claim-title-parcel",
                        document_id=str(document_id),
                        source_engine="granite",
                        anchor=ClaimAnchor(
                            page_number=1,
                            semantic_region_id=str(claimed_region_id),
                        ),
                        canonical_key="real_estate_title.parcel_id",
                        raw_value="P-123",
                        typed_value="P-123",
                        value_type="identifier",
                        confidence=0.8,
                        method="granite_generic_kvp.v1",
                    ),
                ),
            ),
        ],
    )

    assert projection is not None
    assert projection.metadata["skipped_region_extractions"] == [
        {
            "extraction_id": str(unclaimed_extraction_id),
            "semantic_region_id": str(unclaimed_region_id),
            "semantic_type": "generic_form_kvp",
            "reason": "claims_required_for_document_observation_aggregate",
        }
    ]
    assert projection.metadata["source_families"] == ["real_estate_title"]


def test_claim_region_projection_skips_incompatible_first_class_regions() -> None:
    document_id = uuid4()
    invoice_region_id = uuid4()
    eob_region_id = uuid4()
    invoice_extraction_id = uuid4()

    projection = resolve_claim_regions_for_family(
        family="medical_eob",
        missing_claims_reason="claims_required_for_medical_eob_aggregate",
        regions=[
            RegionExtraction(
                extraction_id=invoice_extraction_id,
                semantic_region_id=invoice_region_id,
                semantic_type="invoice_line_item_table",
                claims=(
                    Claim(
                        claim_id="claim-invoice-total",
                        document_id=str(document_id),
                        source_engine="granite",
                        anchor=ClaimAnchor(
                            page_number=1,
                            semantic_region_id=str(invoice_region_id),
                        ),
                        canonical_key="invoice.total_amount",
                        raw_value='{"amount":42.0,"currency":"USD"}',
                        typed_value={"amount": 42.0, "currency": "USD"},
                        value_type="money",
                        confidence=0.9,
                        method="granite_invoice_line_items.v1",
                    ),
                ),
            ),
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=eob_region_id,
                semantic_type="covered_services_line_item_table",
                claims=(
                    Claim(
                        claim_id="claim-eob-payer",
                        document_id=str(document_id),
                        source_engine="granite",
                        anchor=ClaimAnchor(
                            page_number=1,
                            semantic_region_id=str(eob_region_id),
                        ),
                        canonical_key="medical_eob.payer.display_name",
                        raw_value="Anthem Blue Cross",
                        typed_value="Anthem Blue Cross",
                        value_type="text",
                        confidence=0.92,
                        method="granite_medical_service_lines.v1",
                    ),
                ),
            ),
        ],
    )

    assert projection is not None
    assert projection.claim_projection.fields["payer"]["display_name"] == "Anthem Blue Cross"
    assert projection.metadata["source_families"] == ["medical_eob"]
    assert projection.metadata["skipped_region_extractions"] == [
        {
            "extraction_id": str(invoice_extraction_id),
            "semantic_region_id": str(invoice_region_id),
            "semantic_type": "invoice_line_item_table",
            "reason": "aggregate_incompatible_source_family",
            "source_families": ["invoice"],
        }
    ]


def test_dotless_observation_claims_aggregate_into_document_observation() -> None:
    from uuid import uuid4

    from lib.extraction.claims import claims_from_region_envelope
    from lib.extraction.region_envelope import (
        EvidenceRef,
        RegionExtractionEnvelope,
        RegionFact,
    )
    from lib.extraction.region_reconciliation import RegionExtraction

    document_id = str(uuid4())
    region_id = str(uuid4())
    envelope = RegionExtractionEnvelope(
        document_id=document_id,
        semantic_region_id=region_id,
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
                        document_id=document_id,
                        semantic_region_id=region_id,
                        page_number=1,
                        element_id="el-1",
                        source_text="0176595130",
                        source_engine="granite_vision_3b",
                    )
                ],
            )
        ],
    )
    region = RegionExtraction(
        extraction_id=uuid4(),
        semantic_region_id=uuid4(),
        semantic_type="escrow_summary",
        region_envelope=envelope,
        claims=tuple(claims_from_region_envelope(envelope)),
    )

    projection = resolve_claim_regions_for_family(
        family="document_observation",
        missing_claims_reason="claims_required",
        regions=[region],
    )

    assert projection is not None
    assert projection.region_count == 1
    assert [item["field_name"] for item in projection.claim_projection.observations] == [
        "loan_number"
    ]


def test_receipt_compatible_retail_order_regions_aggregate_as_observations() -> None:
    document_id = uuid4()
    region_id = uuid4()
    extraction_id = uuid4()
    anchor = ClaimAnchor(
        page_number=2,
        semantic_region_id=str(region_id),
        table_id="retail-order-table",
        row_index=1,
    )

    projection = resolve_claim_regions_for_family(
        family="document_observation",
        missing_claims_reason="claims_required_for_document_observation_aggregate",
        regions=[
            RegionExtraction(
                extraction_id=extraction_id,
                semantic_region_id=region_id,
                semantic_type="retail_order_line_item_table",
                claims=(
                    Claim(
                        claim_id="claim-retail-merchant",
                        document_id=str(document_id),
                        source_engine="docling",
                        anchor=anchor,
                        canonical_key="retail_order.merchant_name",
                        raw_value="Apple Store",
                        typed_value="Apple Store",
                        value_type="text",
                        confidence=0.91,
                        method="docling_text_table.v1",
                    ),
                    Claim(
                        claim_id="claim-retail-line",
                        document_id=str(document_id),
                        source_engine="docling",
                        anchor=anchor,
                        canonical_key="retail_order.line_item.description",
                        raw_value="Replacement charging cable",
                        typed_value="Replacement charging cable",
                        value_type="text",
                        confidence=0.91,
                        method="docling_text_table.v1",
                    ),
                ),
            )
        ],
    )

    assert projection is not None
    assert projection.region_count == 1
    assert projection.metadata["source_families"] == ["retail_order"]
    observations = {
        (item["family"], item["field_name"]) for item in projection.claim_projection.observations
    }
    assert observations == {
        ("retail_order", "line_item.description"),
        ("retail_order", "merchant_name"),
    }
