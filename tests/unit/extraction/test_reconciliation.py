from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.reconciliation import (
    RegionExtraction,
    reconcile_invoice_region_extractions,
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
                    "line_items": [
                        {
                            "ordinal": 1,
                            "description": "PERFORM 600 MILE RUNNING-IN CHECK",
                            "amount": {"amount": 250.00, "currency": "USD"},
                            "evidence": [{"page_number": 1}],
                        },
                        {
                            "ordinal": 2,
                            "description": "MOUNT AND BALANCE FRONT AND REAR TIRES",
                            "amount": {"amount": 465.48, "currency": "USD"},
                            "evidence": [{"page_number": 1}],
                        },
                    ],
                    "totals": {"total": {"amount": 795.55, "currency": "USD"}},
                },
            ),
            RegionExtraction(
                extraction_id=payment_extraction_id,
                semantic_region_id=payment_region_id,
                semantic_type="payment_summary",
                normalized_json={
                    "invoice_no": "6064658",
                    "amount": "$795.55",
                    "card_number": "**********11108",
                    "auth_code": "000268P",
                },
            ),
        ],
    )

    assert [item["description"] for item in aggregate["line_items"]] == [
        "PERFORM 600 MILE RUNNING-IN CHECK",
        "MOUNT AND BALANCE FRONT AND REAR TIRES",
    ]
    assert aggregate["invoice"]["invoice_number"] == "6064658"
    assert aggregate["totals"]["amount_paid"] == {"amount": 795.55, "currency": "USD"}
    assert aggregate["metadata"]["payment_summary"]["card_number"] == "**********11108"
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
