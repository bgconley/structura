from __future__ import annotations

from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.claims import Claim, ClaimAnchor, ClaimSourceEngine


def test_receipt_claim_resolver_uses_discount_in_total_arithmetic() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="receipt-summary", row_index=1)

    projection = resolve_claims_for_family(
        family="receipt",
        claims=[
            _claim(
                canonical_key="receipt.transaction.subtotal",
                typed_value={"amount": 20.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.transaction.tax",
                typed_value={"amount": 2.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.transaction.tip",
                typed_value={"amount": 3.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.transaction.discount_total",
                typed_value={"amount": 5.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.transaction.total",
                typed_value={"amount": 20.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
        ],
    )

    assert projection.fields["transaction"] == {
        "subtotal": {"amount": 20.0, "currency": "USD"},
        "tax": {"amount": 2.0, "currency": "USD"},
        "tip": {"amount": 3.0, "currency": "USD"},
        "discount_total": {"amount": 5.0, "currency": "USD"},
        "total": {"amount": 20.0, "currency": "USD"},
    }
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } == {
        ("receipt.transaction.discount_total", "accepted", "single_source"),
        ("receipt.transaction.subtotal", "accepted", "single_source"),
        ("receipt.transaction.tax", "accepted", "single_source"),
        ("receipt.transaction.tip", "accepted", "single_source"),
        ("receipt.transaction.total", "accepted", "single_source"),
    }
    assert projection.quality_outcome == "extracted_cleanly"


def test_receipt_claim_resolver_demotes_total_when_discount_is_ignored() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="receipt-summary", row_index=1)

    projection = resolve_claims_for_family(
        family="receipt",
        claims=[
            _claim(
                canonical_key="receipt.transaction.subtotal",
                typed_value={"amount": 20.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.transaction.tax",
                typed_value={"amount": 2.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.transaction.tip",
                typed_value={"amount": 3.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.transaction.discount_total",
                typed_value={"amount": 5.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="receipt.transaction.total",
                typed_value={"amount": 25.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
        ],
    )

    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        ("receipt.transaction.total", "needs_review", "cross_field_arithmetic_conflict"),
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
