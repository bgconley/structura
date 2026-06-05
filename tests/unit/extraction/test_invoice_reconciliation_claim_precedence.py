from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.reconciliation import reconcile_invoice_region_extractions
from lib.extraction.region_envelope import RegionFact, RegionLineItem
from tests.unit.extraction.invoice_reconciliation_fixtures import evidence, invoice_region


def test_invoice_region_reconciliation_uses_claims_over_raw_payload() -> None:
    document_id = uuid4()
    region_id = uuid4()
    region_evidence = evidence(document_id, region_id, row_index=4, table_id="table-7")

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            invoice_region(
                document_id=document_id,
                extraction_id=uuid4(),
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
                facts=[
                    RegionFact(
                        name="invoice.total_amount",
                        value={"amount": 125.0, "currency": "USD"},
                        value_type="money",
                        evidence=[region_evidence],
                    )
                ],
                line_items=[
                    RegionLineItem(
                        description="Anchored service",
                        net_amount=125.0,
                        currency_code="USD",
                        evidence=[region_evidence],
                        table_id="table-7",
                        row_index=4,
                        page_number=1,
                    )
                ],
            ),
        ],
    )

    assert aggregate is not None
    assert [item["description"] for item in aggregate["line_items"]] == ["Anchored service"]
    assert aggregate["line_items"][0]["amount"] == {"amount": 125.0, "currency": "USD"}
    assert aggregate["line_items"][0]["evidence"][0]["table_id"] == "table-7"
    assert aggregate["totals"]["total"] == {"amount": 125.0, "currency": "USD"}


def test_invoice_region_reconciliation_ignores_conflicting_raw_payload() -> None:
    document_id = uuid4()
    region_id = uuid4()
    region_evidence = evidence(document_id, region_id, row_index=2, table_id="table-8")

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            invoice_region(
                document_id=document_id,
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
                facts=[
                    RegionFact(
                        name="invoice.total_amount",
                        value={"amount": 64.0, "currency": "USD"},
                        value_type="money",
                        evidence=[region_evidence],
                    )
                ],
                line_items=[
                    RegionLineItem(
                        description="Claim service",
                        net_amount=64.0,
                        currency_code="USD",
                        evidence=[region_evidence],
                        table_id="table-8",
                        row_index=2,
                        page_number=1,
                    )
                ],
            ),
        ],
    )

    assert aggregate is not None
    assert [item["description"] for item in aggregate["line_items"]] == ["Claim service"]
    assert aggregate["line_items"][0]["amount"] == {"amount": 64.0, "currency": "USD"}
    assert aggregate["totals"]["total"] == {"amount": 64.0, "currency": "USD"}
    assert aggregate["metadata"]["quality_outcome"] == "extracted_cleanly"
