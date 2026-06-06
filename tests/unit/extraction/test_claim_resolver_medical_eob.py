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


def test_medical_eob_claim_resolver_projects_service_line_allowed_and_plan_paid() -> None:
    anchor = ClaimAnchor(page_number=2, table_id="eob-service-lines", row_index=4)

    projection = resolve_claims_for_family(
        family="medical_eob",
        claims=[
            _claim(
                canonical_key="medical_eob.payer.display_name",
                typed_value="Anthem Blue Cross",
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.patient.display_name",
                typed_value="Jane Patient",
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.line_item.description",
                typed_value="Office visit",
                source_engine="granite",
                anchor=anchor,
                group_id="service-line-1",
            ),
            _claim(
                canonical_key="medical_eob.line_item.allowed_amount",
                typed_value={"amount": 80.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
                group_id="service-line-1",
            ),
            _claim(
                canonical_key="medical_eob.line_item.plan_paid",
                typed_value={"amount": 50.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
                group_id="service-line-1",
            ),
            _claim(
                canonical_key="medical_eob.line_item.amount",
                typed_value={"amount": 30.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
                group_id="service-line-1",
            ),
        ],
    )

    assert projection.line_items == [
        {
            "service_description": "Office visit",
            "allowed_amount": {"amount": 80.0, "currency": "USD"},
            "plan_paid": {"amount": 50.0, "currency": "USD"},
            "patient_responsibility": {"amount": 30.0, "currency": "USD"},
            "evidence": [{"page_number": 2, "table_id": "eob-service-lines", "row_index": 4}],
        }
    ]
    assert projection.quality_outcome == "extracted_cleanly"


def test_medical_eob_claim_resolver_demotes_summary_plausibility_conflicts() -> None:
    anchor = ClaimAnchor(page_number=2, table_id="eob-summary", row_index=1)

    projection = resolve_claims_for_family(
        family="medical_eob",
        claims=[
            _claim(
                canonical_key="medical_eob.payer.display_name",
                typed_value="Anthem Blue Cross",
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.patient.display_name",
                typed_value="Jane Patient",
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.total_allowed",
                typed_value={"amount": 80.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.total_plan_paid",
                typed_value={"amount": 75.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.total_patient_responsibility",
                typed_value={"amount": 30.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
        ],
    )

    assert projection.fields["financial_summary"] == {
        "total_allowed": {"amount": 80.0, "currency": "USD"},
        "total_plan_paid": {"amount": 75.0, "currency": "USD"},
        "total_patient_responsibility": {"amount": 30.0, "currency": "USD"},
    }
    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } >= {
        (
            "medical_eob.total_allowed",
            "needs_review",
            "cross_field_plausibility_conflict",
        )
    }
    assert projection.quality_outcome == "needs_human_review"


def test_medical_eob_claim_resolver_allows_summary_rounding_tolerance() -> None:
    anchor = ClaimAnchor(page_number=2, table_id="eob-summary", row_index=1)

    projection = resolve_claims_for_family(
        family="medical_eob",
        claims=[
            _claim(
                canonical_key="medical_eob.payer.display_name",
                typed_value="Anthem Blue Cross",
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.patient.display_name",
                typed_value="Jane Patient",
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.total_allowed",
                typed_value={"amount": 100.0, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.total_plan_paid",
                typed_value={"amount": 80.01, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
            _claim(
                canonical_key="medical_eob.total_patient_responsibility",
                typed_value={"amount": 20.01, "currency": "USD"},
                source_engine="granite",
                anchor=anchor,
            ),
        ],
    )

    assert {
        (decision.canonical_key, decision.decision, decision.reason_code)
        for decision in projection.decisions
    } == {
        ("medical_eob.patient.display_name", "accepted", "single_source"),
        ("medical_eob.payer.display_name", "accepted", "single_source"),
        ("medical_eob.total_allowed", "accepted", "single_source"),
        ("medical_eob.total_patient_responsibility", "accepted", "single_source"),
        ("medical_eob.total_plan_paid", "accepted", "single_source"),
    }
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
