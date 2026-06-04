from __future__ import annotations

from lib.documents.analysis_intake import build_phase9_document_intake


def test_phase9_intake_preserves_explicit_user_confirmed_facts_as_truth() -> None:
    confirmed_fact = {
        "id": "fact-1",
        "fieldPath": "invoice.payment_status",
        "value": "paid",
        "sourceKind": "human",
        "evidence": [_concrete_evidence()],
    }

    intake = build_phase9_document_intake(
        {
            "id": "doc-user-confirmed",
            "userConfirmedFacts": [confirmed_fact],
        }
    )

    assert intake["truth"]["userConfirmedFacts"] == [
        {
            **confirmed_fact,
            "surface": "truth",
        }
    ]
    assert intake["documentQuality"]["canonical_fact_count"] == 1
    assert intake["eligibility"] == "analysis_enabled_with_uncertainty"


def _concrete_evidence() -> dict[str, object]:
    return {
        "pageNumber": 1,
        "elementId": "element-1",
        "sourceEngine": "human_review",
        "sourceText": "Payment marked paid by reviewer.",
    }
