from __future__ import annotations

from uuid import uuid4

from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.claims import ClaimAnchor, claims_from_region_envelope
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionLineItem,
)


def _region_evidence(
    document_id: str,
    region_id: str,
    *,
    row_index: int | None = None,
) -> EvidenceRef:
    return EvidenceRef(
        document_id=document_id,
        semantic_region_id=region_id,
        page_number=1,
        element_id="region-element-7",
        bbox=[10.0, 20.0, 400.0, 300.0],
        row_index=row_index,
        source_engine="granite_vision_3b",
    )


def _receipt_envelope(
    document_id: str,
    region_id: str,
    line_items: list[RegionLineItem],
) -> RegionExtractionEnvelope:
    return RegionExtractionEnvelope(
        document_id=document_id,
        semantic_region_id=region_id,
        resolved_document_type="receipt",
        semantic_type="receipt_line_item_table",
        target_schema="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        line_items=line_items,
    )


def test_distinct_rows_sharing_region_anchor_keep_distinct_groups() -> None:
    document_id = str(uuid4())
    region_id = str(uuid4())
    evidence = _region_evidence(document_id, region_id)
    rows = [
        ("COFFEE", 3.5),
        ("BAGEL", 2.25),
        ("ORANGE JUICE", 4.0),
    ]
    envelope = _receipt_envelope(
        document_id,
        region_id,
        [
            RegionLineItem(
                description=description,
                quantity=1.0,
                net_amount=amount,
                evidence=[evidence],
                page_number=1,
            )
            for description, amount in rows
        ],
    )

    claims = claims_from_region_envelope(envelope)
    description_claims = [
        claim for claim in claims if claim.canonical_key == "receipt.line_item.description"
    ]
    assert len({claim.group_id for claim in description_claims}) == 3

    projection = resolve_claims_for_family(family="receipt", claims=claims)
    assert sorted(
        (item["description"], item["amount"]["amount"]) for item in projection.line_items
    ) == [("BAGEL", 2.25), ("COFFEE", 3.5), ("ORANGE JUICE", 4.0)]


def test_identical_repeated_rows_survive_as_separate_line_items() -> None:
    document_id = str(uuid4())
    region_id = str(uuid4())
    evidence = _region_evidence(document_id, region_id)
    envelope = _receipt_envelope(
        document_id,
        region_id,
        [
            RegionLineItem(
                description="COFFEE",
                quantity=1.0,
                net_amount=3.5,
                evidence=[evidence],
                page_number=1,
            ),
            RegionLineItem(
                description="COFFEE",
                quantity=1.0,
                net_amount=3.5,
                evidence=[evidence],
                page_number=1,
            ),
        ],
    )

    claims = claims_from_region_envelope(envelope)
    description_claims = [
        claim for claim in claims if claim.canonical_key == "receipt.line_item.description"
    ]
    assert len({claim.group_id for claim in description_claims}) == 2

    projection = resolve_claims_for_family(family="receipt", claims=claims)
    assert [item["description"] for item in projection.line_items] == ["COFFEE", "COFFEE"]


def test_claim_identity_ignores_semantic_region_id() -> None:
    document_id = str(uuid4())
    first_region = str(uuid4())
    second_region = str(uuid4())

    def envelope_for(region_id: str) -> RegionExtractionEnvelope:
        return _receipt_envelope(
            document_id,
            region_id,
            [
                RegionLineItem(
                    description="COFFEE",
                    quantity=1.0,
                    net_amount=3.5,
                    evidence=[
                        EvidenceRef(
                            document_id=document_id,
                            semantic_region_id=region_id,
                            page_number=1,
                            table_id="receipt-table",
                            row_index=2,
                            source_engine="granite_vision_3b",
                        )
                    ],
                    page_number=1,
                    table_id="receipt-table",
                    row_index=2,
                )
            ],
        )

    first_claims = claims_from_region_envelope(envelope_for(first_region))
    second_claims = claims_from_region_envelope(envelope_for(second_region))
    first_by_key = {claim.canonical_key: claim for claim in first_claims}
    second_by_key = {claim.canonical_key: claim for claim in second_claims}

    assert first_by_key.keys() == second_by_key.keys()
    for canonical_key, claim in first_by_key.items():
        assert claim.claim_id == second_by_key[canonical_key].claim_id
        assert claim.group_id == second_by_key[canonical_key].group_id

    projection = resolve_claims_for_family(
        family="receipt",
        claims=[*first_claims, *second_claims],
    )
    assert [item["description"] for item in projection.line_items] == ["COFFEE"]


def test_line_items_project_in_numeric_row_order() -> None:
    document_id = str(uuid4())
    region_id = str(uuid4())
    rows = [(10, "ROW TEN"), (2, "ROW TWO"), (1, "ROW ONE")]
    envelope = _receipt_envelope(
        document_id,
        region_id,
        [
            RegionLineItem(
                description=description,
                quantity=1.0,
                net_amount=float(row_index),
                evidence=[
                    EvidenceRef(
                        document_id=document_id,
                        semantic_region_id=region_id,
                        page_number=1,
                        table_id="receipt-table",
                        row_index=row_index,
                        source_engine="granite_vision_3b",
                    )
                ],
                page_number=1,
                table_id="receipt-table",
                row_index=row_index,
            )
            for row_index, description in rows
        ],
    )

    projection = resolve_claims_for_family(
        family="receipt",
        claims=claims_from_region_envelope(envelope),
    )
    assert [item["description"] for item in projection.line_items] == [
        "ROW ONE",
        "ROW TWO",
        "ROW TEN",
    ]


def test_anchor_identity_json_excludes_semantic_region_id() -> None:
    anchor = ClaimAnchor(
        page_number=1,
        table_id="table-1",
        row_index=2,
        semantic_region_id="region-1",
    )
    assert "semantic_region_id" not in anchor.identity_json()
    assert anchor.as_json()["semantic_region_id"] == "region-1"


def test_date_claims_normalize_to_iso() -> None:
    document_id = str(uuid4())
    region_id = str(uuid4())
    envelope = RegionExtractionEnvelope(
        document_id=document_id,
        semantic_region_id=region_id,
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        line_items=[
            RegionLineItem(
                description="Service visit",
                net_amount=12.0,
                service_date="09/10/2025",
                evidence=[
                    EvidenceRef(
                        document_id=document_id,
                        semantic_region_id=region_id,
                        page_number=1,
                        table_id="summary-table",
                        row_index=1,
                        source_engine="granite_vision_3b",
                    )
                ],
            )
        ],
    )

    claims = {
        claim.canonical_key: claim.typed_value for claim in claims_from_region_envelope(envelope)
    }
    assert claims["invoice.line_item.service_date"] == "2025-09-10"


def test_arithmetic_invariant_skips_inconclusive_missing_optional_addend() -> None:
    from lib.extraction.claim_resolver import resolve_claims_for_family as _resolve
    from lib.extraction.claims import Claim

    anchor = ClaimAnchor(page_number=1, table_id="receipt-summary", row_index=1)

    def _claim(canonical_key: str, amount: float) -> Claim:
        return Claim(
            claim_id=f"claim-{canonical_key}",
            document_id="doc-1",
            source_engine="granite",
            anchor=anchor,
            canonical_key=canonical_key,
            raw_value=str(amount),
            typed_value={"amount": amount},
            value_type="money",
            confidence=None,
            method="granite_payment_summary.v1",
        )

    # Total exceeds subtotal but tax/tip were not extracted: the gap is
    # explainable by a missing optional addend, so the total is not demoted.
    projection = _resolve(
        family="receipt",
        claims=[
            _claim("receipt.transaction.subtotal", 10.0),
            _claim("receipt.transaction.total", 11.0),
        ],
    )
    total_decisions = [
        decision
        for decision in projection.decisions
        if decision.canonical_key == "receipt.transaction.total"
    ]
    assert [decision.decision for decision in total_decisions] == ["accepted"]


def test_aggregate_line_items_reject_prompt_echo_content() -> None:
    document_id = str(uuid4())
    region_id = str(uuid4())
    envelope = _receipt_envelope(
        document_id,
        region_id,
        [
            RegionLineItem(
                description="Return ONLY the JSON object for the table schema",
                quantity=1.0,
                net_amount=1.0,
                evidence=[_region_evidence(document_id, region_id, row_index=1)],
                page_number=1,
                row_index=1,
            ),
            RegionLineItem(
                description="COFFEE",
                quantity=1.0,
                net_amount=3.5,
                evidence=[_region_evidence(document_id, region_id, row_index=2)],
                page_number=1,
                row_index=2,
            ),
        ],
    )

    projection = resolve_claims_for_family(
        family="receipt",
        claims=claims_from_region_envelope(envelope),
    )
    assert [item["description"] for item in projection.line_items] == ["COFFEE"]


def test_aggregate_observations_reject_low_signal_grid_values() -> None:
    from lib.extraction.region_envelope import RegionFact

    document_id = str(uuid4())
    region_id = str(uuid4())
    evidence = EvidenceRef(
        document_id=document_id,
        semantic_region_id=region_id,
        page_number=1,
        element_id="el-1",
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=document_id,
        semantic_region_id=region_id,
        resolved_document_type="document_observation",
        semantic_type="generic_form_kvp",
        target_schema="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        observations=[
            RegionFact(
                name="observation.dimensions",
                value={"rows": 4, "cols": 2},
                value_type="object",
                evidence=[evidence],
            ),
            RegionFact(
                name="observation.account_number",
                value="ACCT-1234",
                value_type="string",
                evidence=[evidence],
            ),
        ],
    )

    projection = resolve_claims_for_family(
        family="document_observation",
        claims=claims_from_region_envelope(envelope),
    )
    field_names = {item["field_name"] for item in projection.observations}
    assert "account_number" in field_names
    assert "dimensions" not in field_names


def test_claim_confidence_normalizes_percent_style_values() -> None:
    from lib.extraction.claims import _normalized_confidence

    assert _normalized_confidence(None) is None
    assert _normalized_confidence(0.72) == 0.72
    assert _normalized_confidence(1.0) == 1.0
    assert _normalized_confidence(85.0) == 0.85
    assert _normalized_confidence(100.0) == 1.0
    assert _normalized_confidence(250.0) is None
    assert _normalized_confidence(-0.5) is None
