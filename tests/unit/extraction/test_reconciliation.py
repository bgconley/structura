from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.reconciliation import (
    RegionExtraction,
    reconcile_invoice_region_extractions,
)
from lib.extraction.region_envelope import (
    RegionFact,
    RegionLineItem,
)
from tests.unit.extraction.invoice_reconciliation_fixtures import (
    evidence as _evidence,
)
from tests.unit.extraction.invoice_reconciliation_fixtures import (
    invoice_region as _invoice_region,
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
            _invoice_region(
                document_id=document_id,
                extraction_id=line_extraction_id,
                semantic_region_id=line_region_id,
                semantic_type="invoice_line_item_table",
                facts=[
                    RegionFact(
                        name="invoice.total_amount",
                        value={"amount": 795.55, "currency": "USD"},
                        value_type="money",
                        evidence=[_evidence(document_id, line_region_id, row_index=1)],
                    )
                ],
                line_items=[
                    RegionLineItem(
                        description="PERFORM 600 MILE RUNNING-IN CHECK",
                        net_amount=250.0,
                        currency_code="USD",
                        evidence=[_evidence(document_id, line_region_id, row_index=1)],
                        table_id="table-1",
                        row_index=1,
                        page_number=1,
                    ),
                    RegionLineItem(
                        description="MOUNT AND BALANCE FRONT AND REAR TIRES",
                        net_amount=465.48,
                        currency_code="USD",
                        evidence=[_evidence(document_id, line_region_id, row_index=2)],
                        table_id="table-1",
                        row_index=2,
                        page_number=1,
                    ),
                ],
            ),
            _invoice_region(
                document_id=document_id,
                extraction_id=payment_extraction_id,
                semantic_region_id=payment_region_id,
                semantic_type="payment_summary",
                facts=[
                    RegionFact(
                        name="invoice.invoice_number",
                        value="6064658",
                        value_type="string",
                        evidence=[_evidence(document_id, payment_region_id, row_index=1)],
                    ),
                    RegionFact(
                        name="invoice.amount_paid",
                        value={"amount": 795.55, "currency": "USD"},
                        value_type="money",
                        evidence=[_evidence(document_id, payment_region_id, row_index=1)],
                    ),
                ],
                coverage={
                    "metadata": {
                        "payment_summary": {
                            "card_number": "**********11108",
                            "auth_code": "000268P",
                        }
                    },
                },
            ),
        ],
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


def test_invoice_region_reconciliation_ignores_document_level_raw_invoice_fallback() -> None:
    document_id = uuid4()

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            _invoice_region(
                document_id=document_id,
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="invoice_line_item_table",
                line_items=[
                    RegionLineItem(
                        description="PERFORM 600 MILE RUNNING-IN CHECK",
                        net_amount=250.0,
                        currency_code="USD",
                        evidence=[_evidence(document_id, uuid4(), row_index=1)],
                        table_id="table-1",
                        row_index=1,
                        page_number=1,
                    )
                ],
            ),
        ],
    )

    assert aggregate is not None
    assert aggregate["invoice"] == {}
    assert "invoice.invoice_number" in aggregate["metadata"]["missing_fields"]


def test_invoice_region_reconciliation_does_not_fabricate_required_fields() -> None:
    document_id = uuid4()
    region_id = uuid4()
    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            _invoice_region(
                document_id=document_id,
                extraction_id=uuid4(),
                semantic_region_id=region_id,
                semantic_type="invoice_line_item_table",
                facts=[
                    RegionFact(
                        name="invoice.total_amount",
                        value={"amount": 250.0, "currency": "USD"},
                        value_type="money",
                        evidence=[_evidence(document_id, region_id, row_index=1)],
                    )
                ],
                line_items=[
                    RegionLineItem(
                        description="PERFORM 600 MILE RUNNING-IN CHECK",
                        net_amount=250.0,
                        currency_code="USD",
                        evidence=[_evidence(document_id, region_id, row_index=1)],
                        table_id="table-1",
                        row_index=1,
                        page_number=1,
                    )
                ],
            ),
        ],
    )

    assert aggregate is not None
    assert "invoice_number" not in aggregate["invoice"]
    assert "invoice.invoice_number" in aggregate["metadata"]["missing_fields"]
    assert aggregate["line_items"][0]["description"] == "PERFORM 600 MILE RUNNING-IN CHECK"
    assert aggregate["validation"]["needs_review"] is True


def test_invoice_region_reconciliation_collapses_duplicate_line_items_from_same_evidence() -> None:
    document_id = uuid4()
    region_id = uuid4()

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            _invoice_region(
                document_id=document_id,
                extraction_id=uuid4(),
                semantic_region_id=region_id,
                semantic_type="invoice_line_item_table",
                line_items=[
                    RegionLineItem(
                        description="PERFORM 600 MILE RUNNING-IN CHECK",
                        net_amount=250.0,
                        currency_code="USD",
                        evidence=[_evidence(document_id, region_id, row_index=3)],
                        table_id="table-1",
                        row_index=3,
                        page_number=1,
                    ),
                    RegionLineItem(
                        description=" perform 600 mile running-in check ",
                        net_amount=250.0,
                        currency_code="USD",
                        evidence=[_evidence(document_id, region_id, row_index=3)],
                        table_id="table-1",
                        row_index=3,
                        page_number=1,
                    ),
                ],
            ),
        ],
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
    document_id = uuid4()
    region_id = uuid4()
    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "Health Plan", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            _invoice_region(
                document_id=document_id,
                extraction_id=uuid4(),
                semantic_region_id=region_id,
                semantic_type="covered_services_line_item_table",
                target_schema="medical_eob",
                resolved_document_type="medical_eob",
                line_items=[
                    RegionLineItem(
                        description="Office visit",
                        net_amount=120.0,
                        currency_code="USD",
                        evidence=[_evidence(document_id, region_id, row_index=1)],
                        table_id="table-1",
                        row_index=1,
                        page_number=1,
                    )
                ],
            ),
        ],
    )

    assert aggregate is None


def test_invoice_region_reconciliation_requires_non_placeholder_seller() -> None:
    document_id = uuid4()
    region_id = uuid4()
    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={},
        created_at=datetime.now(UTC),
        regions=[
            _invoice_region(
                document_id=document_id,
                extraction_id=uuid4(),
                semantic_region_id=region_id,
                semantic_type="payment_summary",
                facts=[
                    RegionFact(
                        name="invoice.invoice_number",
                        value="6046058/1",
                        value_type="string",
                        evidence=[_evidence(document_id, region_id, row_index=1)],
                    )
                ],
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
            )
        ],
    )

    assert aggregate is None
