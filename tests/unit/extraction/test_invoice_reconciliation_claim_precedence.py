from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.claims import Claim, ClaimAnchor
from lib.extraction.reconciliation import reconcile_invoice_region_extractions
from lib.extraction.region_envelope import RegionFact, RegionLineItem
from lib.extraction.region_reconciliation import RegionExtraction
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
    assert aggregate["metadata"]["quality_outcome"] == "needs_human_review"
    assert {
        (
            decision["canonical_key"],
            decision["decision"],
            decision["reason_code"],
        )
        for decision in aggregate["metadata"]["claim_resolution_decisions"]
    } >= {
        ("invoice.invoice_number", "absent", "required_claim_absent"),
    }


def test_invoice_region_reconciliation_uses_claim_family_over_raw_schema_label() -> None:
    document_id = uuid4()
    region_id = uuid4()
    group_id = "invoice-row-1"
    anchor = ClaimAnchor(page_number=1, semantic_region_id=str(region_id), row_index=1)

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
                    "schema_name": "medical_eob",
                    "line_items": [{"description": "Raw medical fallback"}],
                },
                claims=(
                    Claim(
                        claim_id="claim-invoice-total",
                        document_id=str(document_id),
                        source_engine="granite",
                        anchor=anchor,
                        canonical_key="invoice.total_amount",
                        raw_value='{"amount":72.0,"currency":"USD"}',
                        typed_value={"amount": 72.0, "currency": "USD"},
                        value_type="money",
                        confidence=0.9,
                        method="granite_invoice_line_items.v1",
                    ),
                    Claim(
                        claim_id="claim-invoice-line-description",
                        document_id=str(document_id),
                        source_engine="granite",
                        anchor=anchor,
                        canonical_key="invoice.line_item.description",
                        raw_value="Anchored labor",
                        typed_value="Anchored labor",
                        value_type="text",
                        confidence=0.9,
                        method="granite_invoice_line_items.v1",
                        group_id=group_id,
                    ),
                    Claim(
                        claim_id="claim-invoice-line-amount",
                        document_id=str(document_id),
                        source_engine="granite",
                        anchor=anchor,
                        canonical_key="invoice.line_item.amount",
                        raw_value='{"amount":72.0,"currency":"USD"}',
                        typed_value={"amount": 72.0, "currency": "USD"},
                        value_type="money",
                        confidence=0.9,
                        method="granite_invoice_line_items.v1",
                        group_id=group_id,
                    ),
                ),
            ),
        ],
    )

    assert aggregate is not None
    assert aggregate["metadata"]["source_families"] == ["invoice"]
    assert aggregate["totals"]["total"] == {"amount": 72.0, "currency": "USD"}
    assert aggregate["line_items"][0]["description"] == "Anchored labor"
