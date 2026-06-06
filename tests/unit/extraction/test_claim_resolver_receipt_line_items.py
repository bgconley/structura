from __future__ import annotations

from uuid import uuid4

from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.claims import (
    Claim,
    ClaimAnchor,
    ClaimSourceEngine,
    claims_from_region_envelope,
)
from lib.extraction.region_envelope import EvidenceRef, RegionExtractionEnvelope, RegionLineItem


def test_receipt_line_item_claims_preserve_discount_and_tax_hint() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="receipt-lines",
        row_index=2,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="receipt",
        semantic_type="receipt_line_item_table",
        target_schema="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        line_items=[
            RegionLineItem(
                description="Coffee beans",
                quantity=2.0,
                unit="bag",
                unit_price=12.0,
                discount_amount=3.0,
                net_amount=21.0,
                currency_code="USD",
                code="BEANS-12",
                tax_category_hint="grocery",
                evidence=[evidence],
                table_id="receipt-lines",
                row_index=2,
                page_number=1,
            )
        ],
    )

    claims = claims_from_region_envelope(envelope)

    assert [claim.canonical_key for claim in claims] == [
        "receipt.line_item.description",
        "receipt.line_item.code",
        "receipt.line_item.quantity",
        "receipt.line_item.unit",
        "receipt.line_item.unit_price",
        "receipt.line_item.discount",
        "receipt.line_item.amount",
        "receipt.line_item.tax_category_hint",
    ]
    assert {claim.canonical_key: claim.typed_value for claim in claims} == {
        "receipt.line_item.description": "Coffee beans",
        "receipt.line_item.code": "BEANS-12",
        "receipt.line_item.quantity": 2.0,
        "receipt.line_item.unit": "bag",
        "receipt.line_item.unit_price": {"amount": 12.0, "currency": "USD"},
        "receipt.line_item.discount": {"amount": 3.0, "currency": "USD"},
        "receipt.line_item.amount": {"amount": 21.0, "currency": "USD"},
        "receipt.line_item.tax_category_hint": "grocery",
    }


def test_receipt_claim_resolver_projects_line_item_discount_and_tax_hint() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="receipt-lines", row_index=2)

    projection = resolve_claims_for_family(
        family="receipt",
        claims=[
            _claim(
                canonical_key="receipt.transaction.total",
                typed_value={"amount": 21.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.line_item.description",
                typed_value="Coffee beans",
                source_engine="granite",
                anchor=anchor,
                group_id="receipt-line-1",
            ),
            _claim(
                canonical_key="receipt.line_item.unit",
                typed_value="bag",
                source_engine="granite",
                anchor=anchor,
                group_id="receipt-line-1",
            ),
            _claim(
                canonical_key="receipt.line_item.discount",
                typed_value={"amount": 3.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
                group_id="receipt-line-1",
            ),
            _claim(
                canonical_key="receipt.line_item.amount",
                typed_value={"amount": 21.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
                group_id="receipt-line-1",
            ),
            _claim(
                canonical_key="receipt.line_item.tax_category_hint",
                typed_value="grocery",
                source_engine="granite",
                anchor=anchor,
                group_id="receipt-line-1",
            ),
        ],
    )

    assert projection.line_items == [
        {
            "description": "Coffee beans",
            "unit": "bag",
            "discount": {"amount": 3.0, "currency": "USD"},
            "amount": {"amount": 21.0, "currency": "USD"},
            "tax_category_hint": "grocery",
            "evidence": [{"page_number": 1, "table_id": "receipt-lines", "row_index": 2}],
        }
    ]
    assert projection.quality_outcome == "extracted_cleanly"


def _claim(
    *,
    canonical_key: str,
    typed_value: object,
    source_engine: ClaimSourceEngine,
    anchor: ClaimAnchor,
    group_id: str | None = None,
) -> Claim:
    return Claim(
        claim_id=f"{source_engine}:{canonical_key}:{typed_value}",
        document_id="doc-1",
        source_engine=source_engine,
        anchor=anchor,
        canonical_key=canonical_key,
        raw_value=str(typed_value),
        typed_value=typed_value,
        value_type="money" if isinstance(typed_value, dict) else "text",
        confidence=0.9,
        method="test",
        group_id=group_id,
        evidence=(anchor.as_json(),),
    )
