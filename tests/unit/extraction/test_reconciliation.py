from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.reconciliation import (
    RegionExtraction,
    reconcile_invoice_region_extractions,
)
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)


def test_invoice_region_reconciliation_preserves_line_items_and_payment_summary() -> None:
    document_id = uuid4()
    line_region_id = uuid4()
    payment_region_id = uuid4()
    line_extraction_id = uuid4()
    payment_extraction_id = uuid4()

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "BMW Motorcycles of Seattle", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=line_extraction_id,
                semantic_region_id=line_region_id,
                semantic_type="invoice_line_item_table",
                normalized_json={
                    "data": {
                        "invoice_line_items": [
                            {
                                "service_description": "PERFORM 600 MILE RUNNING-IN CHECK",
                                "total_due": "250.00",
                            },
                            {
                                "service_type": "MOUNT AND BALANCE FRONT AND REAR TIRES",
                                "service_cost": "465.48",
                            },
                            {
                                "description": "Customer Information",
                                "category_hint": "Customer Information",
                            },
                        ]
                    },
                    "totals": {"total": {"amount": 795.55, "currency": "USD"}},
                },
            ),
            RegionExtraction(
                extraction_id=payment_extraction_id,
                semantic_region_id=payment_region_id,
                semantic_type="payment_summary",
                normalized_json={
                    "invoice": {"invoice_number": "6064658"},
                    "totals": {"amount_paid": {"amount": 795.55, "currency": "USD"}},
                    "metadata": {
                        "payment_summary": {
                            "card_number": "**********11108",
                            "auth_code": "000268P",
                        }
                    },
                },
            ),
        ],
        document_fallback={
            "invoice_number": "6046058/1",
        },
    )

    assert aggregate is not None
    assert [item["description"] for item in aggregate["line_items"]] == [
        "PERFORM 600 MILE RUNNING-IN CHECK",
        "MOUNT AND BALANCE FRONT AND REAR TIRES",
    ]
    assert aggregate["invoice"]["invoice_number"] == "6064658"
    assert aggregate["totals"]["amount_paid"] == {"amount": 795.55, "currency": "USD"}
    assert aggregate["metadata"]["payment_summary"]["card_number"] == "**********11108"
    assert all("extraction_id" not in item for item in aggregate["line_items"][0]["evidence"])
    assert aggregate["metadata"]["region_extractions"] == [
        {
            "extraction_id": str(line_extraction_id),
            "semantic_region_id": str(line_region_id),
            "semantic_type": "invoice_line_item_table",
        },
        {
            "extraction_id": str(payment_extraction_id),
            "semantic_region_id": str(payment_region_id),
            "semantic_type": "payment_summary",
        },
    ]


def test_invoice_region_reconciliation_uses_document_level_invoice_fallback() -> None:
    document_id = uuid4()

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="invoice_line_item_table",
                normalized_json={
                    "line_items": [
                        {
                            "description": "PERFORM 600 MILE RUNNING-IN CHECK",
                            "amount": {"amount": 250.00, "currency": "USD"},
                        }
                    ],
                    "totals": {"total": {"amount": 250.00, "currency": "USD"}},
                },
            ),
        ],
        document_fallback={
            "invoice_number": "6046058/1",
            "date": "04/25/23",
        },
    )

    assert aggregate is not None
    assert aggregate["invoice"]["invoice_number"] == "6046058/1"
    assert aggregate["invoice"]["issued_on"] == "2023-04-25"


def test_invoice_region_reconciliation_does_not_fabricate_required_fields() -> None:
    aggregate = reconcile_invoice_region_extractions(
        document_id=uuid4(),
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="invoice_line_item_table",
                normalized_json={
                    "line_items": [
                        {
                            "description": "PERFORM 600 MILE RUNNING-IN CHECK",
                            "amount": {"amount": 250.00, "currency": "USD"},
                        }
                    ],
                    "totals": {"total": {"amount": 250.00, "currency": "USD"}},
                },
            ),
        ],
    )

    assert aggregate is not None
    assert "invoice_number" not in aggregate["invoice"]
    assert "invoice.invoice_number" in aggregate["metadata"]["missing_fields"]
    assert aggregate["line_items"][0]["description"] == "PERFORM 600 MILE RUNNING-IN CHECK"
    assert aggregate["validation"]["needs_review"] is True


def test_invoice_region_reconciliation_collapses_duplicate_line_items_from_same_evidence() -> None:
    region_id = uuid4()

    aggregate = reconcile_invoice_region_extractions(
        document_id=uuid4(),
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=region_id,
                semantic_type="invoice_line_item_table",
                normalized_json={
                    "schema_name": "invoice",
                    "line_items": [
                        {
                            "description": "PERFORM 600 MILE RUNNING-IN CHECK",
                            "amount": {"amount": 250.00, "currency": "USD"},
                            "table_id": "table-1",
                            "row_index": 3,
                            "page_number": 1,
                            "evidence": [
                                {
                                    "semantic_region_id": str(region_id),
                                    "table_id": "table-1",
                                    "row_index": 3,
                                    "page_number": 1,
                                }
                            ],
                        },
                        {
                            "description": " perform 600 mile running-in check ",
                            "amount": {"amount": 250.00, "currency": "USD"},
                            "table_id": "table-1",
                            "row_index": 3,
                            "page_number": 1,
                            "evidence": [
                                {
                                    "semantic_region_id": str(region_id),
                                    "table_id": "table-1",
                                    "row_index": 3,
                                    "page_number": 1,
                                }
                            ],
                        },
                    ],
                    "totals": {"total": {"amount": 250.00, "currency": "USD"}},
                },
            ),
        ],
        document_fallback={"invoice_number": "6046058/1"},
    )

    assert aggregate is not None
    assert [
        (
            item["ordinal"],
            item["description"],
            item["amount"],
            item["evidence"][0]["row_index"],
        )
        for item in aggregate["line_items"]
    ] == [
        (
            1,
            "PERFORM 600 MILE RUNNING-IN CHECK",
            {"amount": 250.00, "currency": "USD"},
            3,
        )
    ]


def test_invoice_region_reconciliation_skips_incompatible_source_family() -> None:
    aggregate = reconcile_invoice_region_extractions(
        document_id=uuid4(),
        seller={"display_name": "Health Plan", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="invoice_line_item_table",
                normalized_json={
                    "schema_name": "medical_eob",
                    "line_items": [
                        {
                            "description": "Office visit",
                            "amount": {"amount": 120.00, "currency": "USD"},
                            "evidence": [{"page_number": 1}],
                        }
                    ],
                    "totals": {"total": {"amount": 120.00, "currency": "USD"}},
                },
            ),
        ],
    )

    assert aggregate is None


def test_invoice_region_reconciliation_requires_non_placeholder_seller() -> None:
    aggregate = reconcile_invoice_region_extractions(
        document_id=uuid4(),
        seller={},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="payment_summary",
                normalized_json={"invoice": {"invoice_number": "6046058/1"}},
            )
        ],
    )

    assert aggregate is not None
    assert aggregate["seller"] == {}
    assert aggregate["invoice"]["invoice_number"] == "6046058/1"
    assert "seller.display_name" in aggregate["metadata"]["missing_fields"]
    assert aggregate["validation"]["needs_review"] is True


def test_invoice_region_reconciliation_skips_non_invoice_observation_regions() -> None:
    aggregate = reconcile_invoice_region_extractions(
        document_id=uuid4(),
        seller={"display_name": "unknown", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="seller_information_block",
                normalized_json={
                    "schema_name": "document_observation",
                    "observations": [{"field_name": "seller_name", "value": "Jane Seller"}],
                },
            )
        ],
    )

    assert aggregate is None


def test_invoice_region_reconciliation_prefers_typed_envelope_over_raw_payload() -> None:
    document_id = uuid4()
    region_id = uuid4()
    extraction_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="table-7",
        row_index=4,
        source_engine="granite_vision_3b",
    )

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=extraction_id,
                semantic_region_id=region_id,
                semantic_type="invoice_line_item_table",
                normalized_json={
                    "schema_name": "invoice",
                    "line_items": [
                        {
                            "description": "Prompt schema artifact",
                            "amount": {"amount": 999.99, "currency": "USD"},
                        }
                    ],
                    "totals": {"total": {"amount": 999.99, "currency": "USD"}},
                },
                region_envelope=RegionExtractionEnvelope(
                    document_id=str(document_id),
                    semantic_region_id=str(region_id),
                    resolved_document_type="invoice",
                    semantic_type="invoice_line_item_table",
                    target_schema="invoice",
                    model_output_schema_name="granite_invoice_line_items.v1",
                    coverage={"schema_name": "invoice"},
                    facts=[
                        RegionFact(
                            name="invoice.total_amount",
                            value={"amount": 125.0, "currency": "USD"},
                            value_type="money",
                            evidence=[evidence],
                        )
                    ],
                    line_items=[
                        RegionLineItem(
                            description="Anchored service",
                            net_amount=125.0,
                            currency_code="USD",
                            evidence=[evidence],
                            table_id="table-7",
                            row_index=4,
                            page_number=1,
                        )
                    ],
                ),
            ),
        ],
        document_fallback={"invoice_number": "INV-typed"},
    )

    assert aggregate is not None
    assert [item["description"] for item in aggregate["line_items"]] == ["Anchored service"]
    assert aggregate["line_items"][0]["amount"] == {"amount": 125.0, "currency": "USD"}
    assert aggregate["line_items"][0]["evidence"][0]["table_id"] == "table-7"
    assert aggregate["totals"]["total"] == {"amount": 125.0, "currency": "USD"}


def test_invoice_region_reconciliation_prefers_claims_over_envelope_and_raw_payload() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="table-8",
        row_index=2,
        source_engine="granite_vision_3b",
    )
    claim_envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        facts=[
            RegionFact(
                name="invoice.total_amount",
                value={"amount": 64.0, "currency": "USD"},
                value_type="money",
                evidence=[evidence],
            )
        ],
        line_items=[
            RegionLineItem(
                description="Claim service",
                net_amount=64.0,
                currency_code="USD",
                evidence=[evidence],
                table_id="table-8",
                row_index=2,
                page_number=1,
            )
        ],
    )
    conflicting_envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        facts=[
            RegionFact(
                name="invoice.total_amount",
                value={"amount": 999.0, "currency": "USD"},
                value_type="money",
                evidence=[evidence],
            )
        ],
        line_items=[
            RegionLineItem(
                description="Envelope service",
                net_amount=999.0,
                currency_code="USD",
                evidence=[evidence],
                table_id="table-8",
                row_index=2,
                page_number=1,
            )
        ],
    )

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=region_id,
                semantic_type="invoice_line_item_table",
                normalized_json={
                    "schema_name": "invoice",
                    "line_items": [
                        {
                            "description": "Raw service",
                            "amount": {"amount": 1234.0, "currency": "USD"},
                        }
                    ],
                    "totals": {"total": {"amount": 1234.0, "currency": "USD"}},
                },
                region_envelope=conflicting_envelope,
                claims=claims_from_region_envelope(claim_envelope),
            ),
        ],
        document_fallback={"invoice_number": "INV-claims"},
    )

    assert aggregate is not None
    assert [item["description"] for item in aggregate["line_items"]] == ["Claim service"]
    assert aggregate["line_items"][0]["amount"] == {"amount": 64.0, "currency": "USD"}
    assert aggregate["totals"]["total"] == {"amount": 64.0, "currency": "USD"}
