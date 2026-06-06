from __future__ import annotations

from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.claims import Claim, ClaimAnchor, ClaimSourceEngine


def test_medical_eob_claim_resolver_records_absent_required_parties() -> None:
    anchor = ClaimAnchor(page_number=2, table_id="eob-service-lines", row_index=4)
    service_description = _claim(
        canonical_key="medical_eob.line_item.description",
        typed_value="Office visit",
        source_engine="granite",
        anchor=anchor,
        group_id="service-line-1",
    )
    patient_responsibility = _claim(
        canonical_key="medical_eob.line_item.amount",
        typed_value={"amount": 62.0, "currency": "USD"},
        source_engine="granite",
        anchor=anchor,
        group_id="service-line-1",
    )

    projection = resolve_claims_for_family(
        family="medical_eob",
        claims=[service_description, patient_responsibility],
    )

    assert projection.line_items == [
        {
            "service_description": "Office visit",
            "patient_responsibility": {"amount": 62.0, "currency": "USD"},
            "evidence": [{"page_number": 2, "table_id": "eob-service-lines", "row_index": 4}],
        }
    ]
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        ("medical_eob.patient.display_name", "absent", "required_claim_absent"),
        ("medical_eob.payer.display_name", "absent", "required_claim_absent"),
    }
    assert projection.quality_outcome == "needs_human_review"


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
