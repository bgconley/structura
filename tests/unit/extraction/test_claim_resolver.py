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
