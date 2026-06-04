from __future__ import annotations

from lib.documents.analysis_intake import build_phase9_document_intake


def test_phase9_intake_labels_review_required_candidates_as_uncertain() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-1",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "auto_accepted",
                    "evidence": [_evidence()],
                }
            ],
            "fieldCandidates": [
                {
                    "fieldPath": "invoice.seller.display_name",
                    "value": "Acme Services",
                    "status": "needs_review",
                    "evidence": [_evidence()],
                }
            ],
            "lineItemCandidates": [
                {
                    "description": "Labor",
                    "status": "needs_review",
                    "evidence": [_evidence()],
                }
            ],
            "observations": [
                {
                    "observationFamily": "invoice",
                    "fieldName": "ambiguous_note",
                    "status": "needs_review",
                    "value": {"text": "Possible late fee"},
                    "evidence": [_evidence()],
                }
            ],
        }
    )

    assert intake["truth"]["canonicalFields"][0]["fieldPath"] == "invoice.total_amount"
    review_items = (
        intake["review"]["fieldCandidates"]
        + intake["review"]["lineItemCandidates"]
        + intake["review"]["observationCandidates"]
    )
    assert len(review_items) == 3
    assert {item["surface"] for item in review_items} == {"review"}
    assert {item["uncertaintyLabel"] for item in review_items} == {"uncertain_review_required"}


def test_phase9_intake_labels_review_support_surfaces_as_uncertain() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-review-support",
            "fieldCandidates": [
                {
                    "fieldPath": "invoice.seller.display_name",
                    "value": "Acme Services",
                    "status": "needs_review",
                    "evidence": [_concrete_evidence()],
                }
            ],
            "semanticRegionExtractions": [
                {
                    "semanticType": "payment_summary",
                    "reason": "Weak Docling table signal requires review.",
                }
            ],
            "qualitySummary": {"qualityStatus": "review_required"},
            "pages": [
                {
                    "qualitySignals": {
                        "degradedScan": True,
                        "visualEmbeddingEligible": True,
                    }
                }
            ],
        }
    )

    assert intake["review"]["evidenceRefs"] == [
        {
            **_concrete_evidence(),
            "surface": "review",
            "uncertaintyLabel": "uncertain_evidence_ref",
        }
    ]
    assert intake["review"]["plannerExplanations"] == [
        {
            "semanticType": "payment_summary",
            "reason": "Weak Docling table signal requires review.",
            "surface": "review",
            "uncertaintyLabel": "uncertain_planner_explanation",
        }
    ]
    assert intake["review"]["qualitySignals"] == {
        "surface": "review",
        "uncertaintyLabel": "uncertain_quality_signal",
        "document": {"qualityStatus": "review_required"},
        "pages": [{"degradedScan": True, "visualEmbeddingEligible": True}],
    }


def test_phase9_intake_surfaces_planner_task_explanations_for_review() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-planner-review",
            "plannerTasks": [
                {
                    "id": "task-missing-contract",
                    "semanticType": "receipt_line_items",
                    "status": "skipped_missing_contract",
                    "skipReason": "missing_model_output_contract",
                    "contractResolutionReason": "missing_contract",
                    "groundingSummary": {"kind": "table", "pageNumber": 1},
                    "taskJson": {
                        "plannerNote": "Receipt table lacked compatible output schema.",
                        "modelOutputPayload": {"debug": "excluded from review surface"},
                    },
                }
            ],
        }
    )

    assert intake["review"]["plannerExplanations"] == [
        {
            "planTaskId": "task-missing-contract",
            "semanticType": "receipt_line_items",
            "status": "skipped_missing_contract",
            "reason": "missing_model_output_contract",
            "contractResolutionReason": "missing_contract",
            "groundingSummary": {"kind": "table", "pageNumber": 1},
            "surface": "review",
            "uncertaintyLabel": "uncertain_planner_explanation",
        }
    ]


def test_phase9_intake_summarizes_candidate_rejections_for_review() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-candidate-rejections",
            "admissionEvents": [
                {
                    "id": "event-rejected",
                    "decision": "rejected_placeholder_value",
                    "reasons": ["placeholder_or_literal_null"],
                    "candidateKind": "field",
                    "candidateFingerprint": "fingerprint-1",
                    "fieldPath": "invoice.total_amount",
                    "semanticType": "payment_summary",
                    "modelOutputSchemaName": "granite_payment_summary.v1",
                    "sourceEngine": "granite_vision_3b",
                    "payloadJson": {
                        "candidate": {"value": "null"},
                        "rawModelOutput": {"debug": "excluded from review surface"},
                    },
                },
                {
                    "id": "event-admitted",
                    "decision": "admitted",
                    "reasons": [],
                    "candidateKind": "field",
                    "candidateFingerprint": "fingerprint-2",
                },
            ],
        }
    )

    assert intake["review"]["candidateRejections"] == [
        {
            "admissionEventId": "event-rejected",
            "decision": "rejected_placeholder_value",
            "reasons": ["placeholder_or_literal_null"],
            "candidateKind": "field",
            "candidateFingerprint": "fingerprint-1",
            "fieldPath": "invoice.total_amount",
            "semanticType": "payment_summary",
            "modelOutputSchemaName": "granite_payment_summary.v1",
            "sourceEngine": "granite_vision_3b",
            "surface": "review",
            "uncertaintyLabel": "rejected_not_truth",
        }
    ]


def test_phase9_intake_routes_review_required_detail_rows_to_review_surface() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-detail-review",
            "fields": [
                {
                    "fieldPath": "invoice.total_amount",
                    "value": {"amount": 42.5, "currency": "USD"},
                    "reviewStatus": "needs_review",
                    "evidence": [_concrete_evidence()],
                }
            ],
            "lineItems": [
                {
                    "lineItemType": "invoice.service_line",
                    "description": "Labor",
                    "reviewStatus": "needs_review",
                    "evidence": [_concrete_evidence()],
                }
            ],
        }
    )

    assert intake["truth"]["canonicalFields"] == []
    assert intake["truth"]["canonicalLineItems"] == []
    assert intake["documentQuality"]["candidate_count"] == 2
    review_items = intake["review"]["fieldCandidates"] + intake["review"]["lineItemCandidates"]
    assert [item["uncertaintyLabel"] for item in review_items] == [
        "uncertain_review_required",
        "uncertain_review_required",
    ]
    assert intake["eligibility"] == "analysis_enabled_with_uncertainty"


def test_phase9_intake_preserves_observation_candidates_with_truth_observations() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-observation-candidate",
            "observations": [
                {
                    "observationFamily": "invoice",
                    "fieldName": "statement_context",
                    "status": "auto_accepted",
                    "value": {"text": "Monthly statement"},
                    "evidence": [_concrete_evidence()],
                }
            ],
            "observationCandidates": [
                {
                    "observationFamily": "invoice",
                    "fieldName": "possible_discount",
                    "status": "needs_review",
                    "value": {"text": "Possible discount terms"},
                    "evidence": [_concrete_evidence()],
                }
            ],
        }
    )

    assert len(intake["truth"]["canonicalObservations"]) == 1
    assert len(intake["review"]["observationCandidates"]) == 1
    assert intake["documentQuality"]["canonical_fact_count"] == 1
    assert intake["documentQuality"]["candidate_count"] == 1
    assert intake["review"]["uncertainObservations"][0]["fieldName"] == "possible_discount"


def test_phase9_intake_preserves_canonical_alias_truth_with_detail_review_rows() -> None:
    intake = build_phase9_document_intake(
        {
            "id": "doc-mixed-aliases",
            "fields": [
                {
                    "id": "field-review",
                    "fieldPath": "invoice.total_amount",
                    "reviewStatus": "needs_review",
                    "evidence": [_concrete_evidence()],
                }
            ],
            "canonicalFields": [
                {
                    "id": "field-truth",
                    "fieldPath": "invoice.issue_date",
                    "reviewStatus": "auto_accepted",
                    "evidence": [_concrete_evidence()],
                }
            ],
            "lineItems": [
                {
                    "id": "line-review",
                    "lineItemType": "invoice.service_line",
                    "reviewStatus": "needs_review",
                    "evidence": [_concrete_evidence()],
                }
            ],
            "canonicalLineItems": [
                {
                    "id": "line-truth",
                    "lineItemType": "invoice.service_line",
                    "reviewStatus": "auto_accepted",
                    "evidence": [_concrete_evidence()],
                }
            ],
            "observations": [
                {
                    "id": "observation-review",
                    "fieldName": "possible_discount",
                    "status": "needs_review",
                    "evidence": [_concrete_evidence()],
                }
            ],
            "canonicalObservations": [
                {
                    "id": "observation-truth",
                    "fieldName": "statement_context",
                    "status": "auto_accepted",
                    "evidence": [_concrete_evidence()],
                }
            ],
        }
    )

    assert [item["id"] for item in intake["truth"]["canonicalFields"]] == ["field-truth"]
    assert [item["id"] for item in intake["truth"]["canonicalLineItems"]] == ["line-truth"]
    assert [item["id"] for item in intake["truth"]["canonicalObservations"]] == [
        "observation-truth"
    ]
    assert intake["documentQuality"]["canonical_fact_count"] == 3
    assert intake["documentQuality"]["candidate_count"] == 3


def _evidence() -> dict[str, object]:
    return {
        "pageNumber": 1,
        "sourceEngine": "granite_vision_3b",
        "sourceText": "Invoice total $42.50",
    }


def _concrete_evidence() -> dict[str, object]:
    return {
        **_evidence(),
        "elementId": "element-1",
    }
