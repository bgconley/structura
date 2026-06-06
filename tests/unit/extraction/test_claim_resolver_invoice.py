from __future__ import annotations

from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.claims import Claim, ClaimAnchor, ClaimSourceEngine


def test_invoice_claim_resolver_uses_shipping_and_discount_in_total_arithmetic() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="invoice-totals", row_index=1)

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[
            _claim(
                canonical_key="invoice.invoice_number",
                typed_value="INV-42",
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.subtotal",
                typed_value={"amount": 100.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.tax_total",
                typed_value={"amount": 10.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.shipping_total",
                typed_value={"amount": 5.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.discount_total",
                typed_value={"amount": 15.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.total_amount",
                typed_value={"amount": 100.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
        ],
    )

    assert projection.fields["totals"] == {
        "subtotal": {"amount": 100.0, "currency": "USD"},
        "tax_total": {"amount": 10.0, "currency": "USD"},
        "shipping_total": {"amount": 5.0, "currency": "USD"},
        "discount_total": {"amount": 15.0, "currency": "USD"},
        "total": {"amount": 100.0, "currency": "USD"},
    }
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } == {
        ("invoice.discount_total", "accepted", "single_source"),
        ("invoice.invoice_number", "accepted", "single_source"),
        ("invoice.shipping_total", "accepted", "single_source"),
        ("invoice.subtotal", "accepted", "single_source"),
        ("invoice.tax_total", "accepted", "single_source"),
        ("invoice.total_amount", "accepted", "single_source"),
    }
    assert projection.quality_outcome == "extracted_cleanly"


def test_invoice_claim_resolver_demotes_total_when_shipping_discount_are_ignored() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="invoice-totals", row_index=1)

    projection = resolve_claims_for_family(
        family="invoice",
        claims=[
            _claim(
                canonical_key="invoice.invoice_number",
                typed_value="INV-42",
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.subtotal",
                typed_value={"amount": 100.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.tax_total",
                typed_value={"amount": 10.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.shipping_total",
                typed_value={"amount": 5.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.discount_total",
                typed_value={"amount": 15.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="invoice.total_amount",
                typed_value={"amount": 110.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
        ],
    )

    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        ("invoice.total_amount", "needs_review", "cross_field_arithmetic_conflict"),
    }
    assert projection.quality_outcome == "needs_human_review"


def _claim(
    *,
    canonical_key: str,
    typed_value: object,
    source_engine: ClaimSourceEngine,
    anchor: ClaimAnchor,
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
        evidence=(anchor.as_json(),),
    )
