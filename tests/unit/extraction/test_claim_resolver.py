from __future__ import annotations

from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.claims import Claim, ClaimAnchor, ClaimSourceEngine


def test_invoice_claim_resolver_projects_claims_with_source_precedence() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="table-1", row_index=1)
    docling_total = _claim(
        canonical_key="invoice.total_amount",
        typed_value={"amount": 41.0, "currency": "USD"},
        source_engine="docling",
        anchor=anchor,
    )
    granite_total = _claim(
        canonical_key="invoice.total_amount",
        typed_value={"amount": 42.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    line_description = _claim(
        canonical_key="invoice.line_item.description",
        typed_value="Alignment service",
        source_engine="granite",
        anchor=anchor,
        group_id="line-1",
    )
    line_amount = _claim(
        canonical_key="invoice.line_item.amount",
        typed_value={"amount": 42.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="line-1",
    )

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[docling_total, granite_total, line_description, line_amount],
    )

    assert projection.fields["totals"]["total"] == {"amount": 42.0, "currency": "USD"}
    assert projection.line_items == [
        {
            "description": "Alignment service",
            "amount": {"amount": 42.0, "currency": "USD"},
            "evidence": [{"page_number": 1, "table_id": "table-1", "row_index": 1}],
        }
    ]
    assert [
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    ] == [
        ("invoice.line_item.amount", "accepted", "single_source"),
        ("invoice.line_item.description", "accepted", "single_source"),
        ("invoice.total_amount", "needs_review", "source_precedence_conflict"),
    ]


def test_receipt_claim_resolver_projects_registry_fields_and_line_items() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="receipt-table", row_index=2)
    merchant = _claim(
        canonical_key="receipt.merchant.display_name",
        typed_value="Apple Store",
        source_engine="granite",
        anchor=anchor,
    )
    total = _claim(
        canonical_key="receipt.transaction.total",
        typed_value={"amount": 21.63, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )
    line_description = _claim(
        canonical_key="receipt.line_item.description",
        typed_value="USB-C cable",
        source_engine="granite",
        anchor=anchor,
        group_id="receipt-line-1",
    )
    line_sku = _claim(
        canonical_key="receipt.line_item.code",
        typed_value="MU9F2AM/A",
        source_engine="granite",
        anchor=anchor,
        group_id="receipt-line-1",
    )
    line_amount = _claim(
        canonical_key="receipt.line_item.amount",
        typed_value={"amount": 19.98, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="receipt-line-1",
    )
    unsupported_line_tax = _claim(
        canonical_key="receipt.line_item.tax_amount",
        typed_value={"amount": 1.65, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="receipt-line-1",
    )

    projection = resolve_claims_for_family(
        family="receipt",
        claims=[merchant, total, line_description, line_sku, line_amount, unsupported_line_tax],
    )

    assert projection.fields["merchant"] == {"display_name": "Apple Store"}
    assert projection.fields["transaction"] == {"total": {"amount": 21.63, "currency": "USD"}}
    assert projection.line_items == [
        {
            "description": "USB-C cable",
            "sku": "MU9F2AM/A",
            "amount": {"amount": 19.98, "currency": "USD"},
            "evidence": [{"page_number": 1, "table_id": "receipt-table", "row_index": 2}],
        }
    ]
    assert "receipt.line_item.code" in {decision.canonical_key for decision in projection.decisions}
    assert "receipt.line_item.sku" not in {
        decision.canonical_key for decision in projection.decisions
    }


def test_document_observation_claim_resolver_projects_claims_to_observations() -> None:
    anchor = ClaimAnchor(page_number=3, page_id="page-3", docling_element_ids=("el-9",))
    docling_address = _claim(
        canonical_key="real_estate_title.property.address",
        typed_value="123 Main",
        source_engine="docling",
        anchor=anchor,
    )
    granite_address = _claim(
        canonical_key="real_estate_title.property.address",
        typed_value="123 Main St",
        source_engine="granite",
        anchor=anchor,
    )

    projection = resolve_claims_for_family(
        family="document_observation",
        claims=[docling_address, granite_address],
    )

    assert projection.family == "document_observation"
    assert projection.observations == [
        {
            "family": "real_estate_title",
            "field_name": "property.address",
            "value": "123 Main St",
            "value_type": "string",
            "source_text": "123 Main St",
            "confidence": 0.9,
            "evidence": [
                {
                    "page_number": 3,
                    "page_id": "page-3",
                    "docling_element_ids": ["el-9"],
                }
            ],
        }
    ]
    assert [
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    ] == [
        (
            "real_estate_title.property.address",
            "needs_review",
            "source_precedence_conflict",
        )
    ]


def test_unknown_claim_family_degrades_to_document_observation_projection() -> None:
    anchor = ClaimAnchor(page_number=1, text_span={"start": 10, "end": 22})
    claim = _claim(
        canonical_key="mortgage_escrow_statement.shortage_amount",
        typed_value={"amount": 84.25, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
    )

    projection = resolve_claims_for_family(
        family="mortgage_escrow_statement",
        claims=[claim],
    )

    assert projection.family == "document_observation"
    assert projection.observations == [
        {
            "family": "mortgage_escrow_statement",
            "field_name": "shortage_amount",
            "value": {"amount": 84.25, "currency": "USD"},
            "value_type": "json",
            "source_text": "{'amount': 84.25, 'currency': 'USD'}",
            "confidence": 0.9,
            "evidence": [{"page_number": 1, "text_span": {"start": 10, "end": 22}}],
        }
    ]


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
