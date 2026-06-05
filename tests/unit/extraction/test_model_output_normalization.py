from __future__ import annotations

from uuid import uuid4

from lib.extraction.docling_table_quality import DoclingTableQuality
from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_normalization import (
    normalize_granite_region_output,
    observation_dicts_from_payload,
)
from lib.extraction.models import ValidationReport
from lib.extraction.normalization import (
    field_candidates_from_extraction,
    line_item_candidates_from_extraction,
    observation_candidates_from_extraction,
)
from lib.extraction.validators import validate_extraction_payload, validate_semantic_region_payload


def test_normalize_granite_region_output_handles_non_object_payloads_without_crashing() -> None:
    document_id = uuid4()

    for payload in (None, "not json", ["row one", {"field": "value"}]):
        normalized, metadata = normalize_granite_region_output(
            document_id=document_id,
            schema_name="document_observation",
            model_output_schema_name="granite_generic_kvp.v1",
            payload=payload,
        )

        assert normalized["schema_name"] == "document_observation"
        assert normalized["document_id"] == str(document_id)
        assert isinstance(normalized["observations"], list)
        assert metadata["mapper"] == "granite_generic_kvp.v1"
        assert metadata["repairs"]


def test_normalize_granite_region_output_rejects_schema_echo_as_observation_payload() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "properties": {"seller_name": {"type": "string"}},
        },
    )

    assert normalized["observations"] == []
    assert "schema_echo_rejected" in metadata["repairs"]


def test_generic_kvp_output_maps_to_reviewable_observations() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_real_estate_title_seller_info.v1",
        payload={
            "seller_name": "Brennan Conley",
            "property_address": "123 Main St",
            "confidence": {"overall": 0.74},
        },
    )

    assert normalized["schema_name"] == "document_observation"
    assert [item["field_name"] for item in normalized["observations"]] == [
        "seller_name",
        "property_address",
    ]
    assert metadata["mapper"] == "granite_real_estate_title_seller_info.v1"
    assert observation_dicts_from_payload(normalized)[0]["value"] == "Brennan Conley"


def test_review_only_receipt_like_output_defers_broad_observations() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "fields": [
                {"name": "total_amount", "value": "$42.00"},
                {"name": "payment_method", "value": "AMEX CREDIT"},
            ],
            "confidence": {"overall": 0.74},
        },
        semantic_type="receipt_payment_summary",
        target_schema="document_observation",
        resolved_document_type="generic",
    )

    assert normalized["schema_name"] == "document_observation"
    assert normalized["observations"] == []
    assert normalized["metadata"]["deferred_observation_count"] == 2
    assert metadata["deferred_observation_count"] == 2
    assert "deferred_review_only_receipt_like_observations" in metadata["repairs"]


def test_granite_line_item_evidence_uses_region_grounding_context() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    page_id = uuid4()
    table_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={"line_items": [{"description": "Alignment service", "amount": "$99.00"}]},
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=annotation_id,
            semantic_region_id=region_id,
            page_id=page_id,
            page_number=3,
            table_id=table_id,
        ),
    )

    evidence = normalized["line_items"][0]["evidence"][0]
    assert evidence["page_number"] == 3
    assert evidence["page_id"] == str(page_id)
    assert evidence["table_id"] == str(table_id)
    assert evidence["semantic_region_id"] == str(region_id)
    assert evidence["semantic_annotation_id"] == str(annotation_id)
    assert has_concrete_evidence([evidence]) is True


def test_authoritative_docling_table_rejects_line_items_without_row_identity() -> None:
    document_id = uuid4()
    table_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "line_items": [
                {
                    "description": "Grounded row",
                    "row_index": 1,
                    "table_id": str(table_id),
                    "page_number": 2,
                    "amount": "$99.00",
                },
                {"description": "Invented row", "amount": "$12.00"},
            ],
            "confidence": {"overall": 0.81},
        },
        docling_table_quality=DoclingTableQuality(
            table_id=str(table_id),
            page_number=2,
            row_count=3,
            column_count=3,
            non_empty_cell_ratio=0.95,
            header_confidence=0.85,
            numeric_column_count=1,
            bbox_available=True,
            markdown_available=True,
            continuation_risk=False,
            score=0.88,
            route="docling_table_plus_granite_labeler",
        ),
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            table_id=table_id,
            page_number=2,
        ),
    )

    assert [item["description"] for item in normalized["line_items"]] == ["Grounded row"]
    evidence = normalized["line_items"][0]["evidence"][0]
    assert evidence["table_id"] == str(table_id)
    assert evidence["row_index"] == 1
    assert evidence["page_number"] == 2
    assert metadata["tableConsistency"]["rejectedRowCount"] == 1
    rejected_row = metadata["tableConsistency"]["rejectedRows"][0]
    assert rejected_row["reason"] == "candidate.missing_docling_row_index"
    assert rejected_row["payload"]["description"] == "Invented row"
    assert rejected_row["payload"]["amount"] == {"amount": 12.0, "currency": "USD"}
    assert rejected_row["payload"]["table_id"] == str(table_id)
    assert rejected_row["payload"]["page_number"] == 2
    assert "row_index" not in rejected_row["payload"]
    assert (
        normalized["metadata"]["tableConsistency"]["rejectedRows"]
        == metadata["tableConsistency"]["rejectedRows"]
    )
    assert "candidate.missing_docling_row_index" in metadata["tableConsistency"]["warnings"]


def test_receipt_payment_summary_concretizes_region_evidence_and_defers_page_money() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    page_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload={
            "merchant_name": "Coffee Shop",
            "transaction_date": "2026-05-01",
            "subtotal": "$4.25",
            "tax": "$0.40",
            "total": "$4.65",
            "confidence": {},
        },
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=annotation_id,
            semantic_region_id=region_id,
            page_id=page_id,
            page_number=1,
        ),
    )

    assert "attached_region_evidence_context" in metadata["repairs"]
    assert has_concrete_evidence(normalized["transaction"]["evidence"]) is True

    candidates = field_candidates_from_extraction(
        document_id=document_id,
        schema_name="receipt",
        payload=normalized,
        validation=ValidationReport(needs_review=True, checks=[]),
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    assert [candidate.field_path for candidate in candidates] == [
        "receipt.merchant.display_name",
        "receipt.transaction.date_local",
    ]
    assert all(has_concrete_evidence(candidate.evidence) for candidate in candidates)
    assert metadata["deferred_payment_summary_fields"] == ["subtotal", "tax", "total"]


def test_receipt_payment_summary_defers_unanchored_money_candidates_for_repeatability() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload={
            "merchant_name": "Coffee Shop",
            "transaction_date": "2026-05-01",
            "subtotal": "$4.25",
            "tax": "$0.40",
            "total": "$4.65",
            "confidence": {},
        },
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=uuid4(),
            semantic_region_id=uuid4(),
            page_id=uuid4(),
            page_number=1,
        ),
        semantic_type="receipt_payment_summary",
        target_schema="receipt",
        resolved_document_type="receipt",
    )

    candidates = field_candidates_from_extraction(
        document_id=document_id,
        schema_name="receipt",
        payload=normalized,
        validation=ValidationReport(needs_review=True, checks=[]),
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    assert [candidate.field_path for candidate in candidates] == [
        "receipt.merchant.display_name",
        "receipt.transaction.date_local",
    ]
    assert metadata["deferred_payment_summary_fields"] == ["subtotal", "tax", "total"]


def test_receipt_payment_summary_persists_region_envelope_projection() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    page_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload={
            "merchant_name": "Coffee Shop",
            "transaction_date": "2026-05-01",
            "subtotal": "$4.25",
            "tax": "$0.40",
            "total": "$4.65",
            "confidence": {"overall": 0.83},
        },
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=annotation_id,
            semantic_region_id=region_id,
            page_id=page_id,
            page_number=1,
        ),
        semantic_type="receipt_payment_summary",
        target_schema="receipt",
        resolved_document_type="receipt",
    )

    envelope = metadata["regionEnvelope"]
    assert metadata["regionEnvelopeVersion"] == "phase8_5-region-envelope-v1"
    assert metadata["normalizedProjectionDerivedFromEnvelope"] is True
    assert envelope["document_id"] == str(document_id)
    assert envelope["semantic_annotation_id"] == str(annotation_id)
    assert envelope["semantic_region_id"] == str(region_id)
    assert envelope["semantic_type"] == "receipt_payment_summary"
    assert envelope["model_output_schema_name"] == "granite_receipt_payment_summary.v1"
    assert envelope["coverage"]["normalized_projection"] == normalized
    assert {fact["name"] for fact in envelope["facts"]} >= {
        "receipt.merchant.display_name",
        "receipt.transaction.date_local",
    }
    assert metadata["deferred_payment_summary_fields"] == ["subtotal", "tax", "total"]


def test_receipt_payment_summary_parses_model_datetime_before_candidate_insert() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload={
            "merchant_name": "Coffee Shop",
            "transaction_date": "10-Sep-2025 12:17:38P",
            "total": "$4.65",
            "confidence": {},
        },
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=uuid4(),
            semantic_region_id=uuid4(),
            page_id=uuid4(),
            page_number=1,
        ),
    )

    candidates = field_candidates_from_extraction(
        document_id=document_id,
        schema_name="receipt",
        payload=normalized,
        validation=ValidationReport(needs_review=True, checks=[]),
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    dates = [
        candidate.value
        for candidate in candidates
        if candidate.field_path == "receipt.transaction.date_local"
    ]
    assert [value.isoformat() for value in dates] == ["2025-09-10"]


def test_unparseable_receipt_date_is_not_persisted_as_date_candidate() -> None:
    document_id = uuid4()

    candidates = field_candidates_from_extraction(
        document_id=document_id,
        schema_name="receipt",
        payload={
            "schema_name": "receipt",
            "merchant": {
                "display_name": "Coffee Shop",
                "evidence": [
                    {
                        "semantic_region_id": str(uuid4()),
                        "page_number": 1,
                    }
                ],
            },
            "transaction": {
                "date_local": "not a real date",
                "evidence": [
                    {
                        "semantic_region_id": str(uuid4()),
                        "page_number": 1,
                    }
                ],
            },
        },
        validation=ValidationReport(needs_review=True, checks=[]),
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    assert "receipt.transaction.date_local" not in {
        candidate.field_path for candidate in candidates
    }


def test_empty_kvp_output_keeps_region_level_evidence_for_validation() -> None:
    document_id = uuid4()
    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_dispute_form.v1",
        payload={
            "account_holder": None,
            "merchant_name": None,
            "transaction_date": None,
            "transaction_amount": None,
            "dispute_reason": None,
            "transactions": [],
            "confidence": {},
        },
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=uuid4(),
            semantic_region_id=uuid4(),
            page_id=uuid4(),
            page_number=1,
        ),
    )

    assert normalized["observations"] == []
    assert has_concrete_evidence(normalized["evidence"]) is True
    validation = validate_semantic_region_payload(
        normalized,
        model_output_schema_name="granite_dispute_form.v1",
        model_output_payload={
            "account_holder": None,
            "merchant_name": None,
            "transaction_date": None,
            "transaction_amount": None,
            "dispute_reason": None,
            "transactions": [],
            "confidence": {},
        },
    )
    assert [check for check in validation.checks if check["code"] == "evidence.concrete_locator"][
        0
    ]["status"] == "passed"


def test_healthcare_coverage_decision_defers_broad_model_observations() -> None:
    document_id = uuid4()
    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="medical_eob",
        model_output_schema_name="granite_healthcare_coverage_decision.v1",
        payload={
            "facts": [
                {
                    "name": "denial_reason",
                    "value": "Not medically necessary",
                    "confidence": 0.86,
                    "source_text": "not medically necessary",
                }
            ],
            "contacts": [
                {
                    "contact_type": "appeal",
                    "phone": "555-0100",
                    "source_text": "Appeals: 555-0100",
                    "confidence": 0.8,
                }
            ],
            "service_lines": [],
            "warnings": [],
        },
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=uuid4(),
            semantic_region_id=uuid4(),
            page_id=uuid4(),
            page_number=1,
        ),
    )

    assert metadata["mapper"] == "granite_healthcare_coverage_decision.v1"
    assert normalized["schema_name"] == "document_observation"
    assert normalized["observations"] == []
    assert metadata["deferred_observation_count"] == 3
    assert "deferred_unbounded_healthcare_coverage_decision_observations" in metadata["repairs"]


def test_healthcare_coverage_decision_defers_unbounded_observations_for_repeatability() -> None:
    document_id = uuid4()
    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="medical_eob",
        model_output_schema_name="granite_healthcare_coverage_decision.v1",
        payload={
            "facts": [
                {
                    "name": "request_status",
                    "value": "We cannot approve this request.",
                    "confidence": 0.86,
                    "source_text": "we cannot approve this request",
                },
                {
                    "name": "grievance_rights",
                    "value": "You have the right to appeal.",
                    "confidence": 0.8,
                    "source_text": "you have the right to appeal",
                },
            ],
            "contacts": [
                {
                    "name": "Grievances and Appeals",
                    "phone": "1-800-365-0609",
                    "source_text": "Grievances and Appeals 1-800-365-0609",
                    "confidence": 0.8,
                }
            ],
            "service_lines": [],
            "warnings": [],
        },
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=uuid4(),
            semantic_region_id=uuid4(),
            page_id=uuid4(),
            page_number=1,
        ),
    )

    assert normalized["observations"] == []
    assert metadata["deferred_observation_count"] == 4
    assert "deferred_unbounded_healthcare_coverage_decision_observations" in metadata["repairs"]


def test_observation_mapper_drops_schema_and_prompt_echo_fields() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "properties": {"seller_name": {"type": "string"}},
            "instructions": "Return only JSON matching this schema",
            "seller_name": "Jane Seller",
        },
    )

    observations = observation_dicts_from_payload(normalized)
    assert [item["field_name"] for item in observations] == ["seller_name"]


def test_receipt_line_item_model_output_maps_to_canonical_receipt_lines() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        payload={
            "line_items": [
                {
                    "description": "USB-C cable",
                    "quantity": "2",
                    "unit_price": "$9.99",
                    "amount": "$19.98",
                }
            ],
            "totals": {"total": "$21.63"},
            "confidence": {"overall": 0.82},
        },
    )

    assert normalized["schema_name"] == "receipt"
    assert normalized["line_items"][0]["description"] == "USB-C cable"
    assert normalized["line_items"][0]["amount"] == {"amount": 19.98, "currency": "USD"}
    assert normalized["transaction"]["total"] == {"amount": 21.63, "currency": "USD"}
    assert metadata["mapper"] == "granite_receipt_line_items.v1"


def test_service_record_flat_output_maps_to_canonical_receipt_lines() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_service_record_line_items.v1",
        payload={
            "service_description": [
                "PERFORM 600 MILE RUNNING-IN CHECK ACCORDING TO BMWCHECKLIST.",
                "MOUNT AND BALANCE FRONT AND REAR TIRES.DISPOSE OF OLD TIRES.",
            ],
            "labor_operation": ["0000600", "TIRE-SVC"],
            "part_number": [":Gypoid axle oil G3", ":TIRE PR 4SC 160/60R15 67H"],
            "quantity": ["1", "2"],
            "unit_price": ["250.00", "182.99"],
            "line_total": ["250.00", "365.98"],
            "confidence": {"overall": 0.73},
        },
    )

    assert normalized["schema_name"] == "receipt"
    assert [item["description"] for item in normalized["line_items"]] == [
        "PERFORM 600 MILE RUNNING-IN CHECK ACCORDING TO BMWCHECKLIST.",
        "MOUNT AND BALANCE FRONT AND REAR TIRES.DISPOSE OF OLD TIRES.",
        ":Gypoid axle oil G3",
        ":TIRE PR 4SC 160/60R15 67H",
    ]
    assert normalized["line_items"][0]["amount"] == {"amount": 250.0, "currency": "USD"}
    assert normalized["line_items"][2]["quantity"] == 1.0
    assert metadata["mapper"] == "granite_service_record_line_items.v1"


def test_unwrapped_data_payload_preserves_sibling_totals_for_invoice_line_items() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "data": {
                "invoice_line_items": [
                    {
                        "description": "Alignment service",
                        "amount": "$99.00",
                    }
                ]
            },
            "totals": {"total": {"amount": 99.00, "currency": "USD"}},
        },
    )

    assert normalized["line_items"][0]["description"] == "Alignment service"
    assert normalized["totals"]["total"] == {"amount": 99.0, "currency": "USD"}


def test_observation_payload_with_type_object_and_fields_is_not_schema_echo() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "type": "object",
            "fields": [{"name": "seller_name", "value": "Jane Seller"}],
        },
    )

    assert "schema_echo_rejected" not in metadata["repairs"]
    assert observation_dicts_from_payload(normalized)[0]["field_name"] == "seller_name"


def test_observation_source_text_is_bounded_to_schema_limit() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "seller_notes": "x" * 700,
            "confidence": {"overall": 0.61},
        },
    )
    report = validate_extraction_payload("document_observation", normalized)

    assert report.checks[0]["status"] == "passed"
    observations = observation_dicts_from_payload(normalized)
    assert len(observations[0]["source_text"]) == 500


def test_observation_candidate_confidence_rejects_out_of_range_model_values() -> None:
    candidates = observation_candidates_from_extraction(
        schema_name="document_observation",
        payload={
            "observations": [
                {
                    "field_name": "escrow_shortage",
                    "value": "$250.00",
                    "value_type": "string",
                    "confidence": 250.0,
                }
            ]
        },
        validation=ValidationReport(needs_review=True, checks=[]),
    )

    assert len(candidates) == 1
    assert candidates[0].confidence is None


def test_line_item_candidates_drop_exact_and_sparse_duplicates() -> None:
    candidates = line_item_candidates_from_extraction(
        schema_name="receipt",
        payload={
            "line_items": [
                {
                    "ordinal": 1,
                    "description": "OBEN SPA-1000 SMARTPHONE ADAPTER",
                    "quantity": 1,
                    "unit_price": {"amount": 120.32, "currency": "USD"},
                    "amount": {"amount": 120.32, "currency": "USD"},
                },
                {
                    "ordinal": 2,
                    "description": "OBEN SPA-1000 SMARTPHONE ADAPTER",
                    "quantity": 1,
                    "unit_price": {"amount": 120.32, "currency": "USD"},
                    "amount": {"amount": 120.32, "currency": "USD"},
                },
                {
                    "ordinal": 3,
                    "description": "OBEN SPA-1000 SMARTPHONE ADAPTER",
                },
                {
                    "ordinal": 4,
                    "description": "OBEN SPA-1000 SMARTPHONE ADAPTER",
                    "quantity": 1,
                    "unit_price": {"amount": 20.0, "currency": "USD"},
                    "amount": {"amount": 20.0, "currency": "USD"},
                },
                {
                    "ordinal": 5,
                    "description": "OBEN CTT-1000 CF TABLETOP TRIPOD",
                    "quantity": 1,
                    "unit_price": {"amount": 103.9, "currency": "USD"},
                    "amount": {"amount": 103.9, "currency": "USD"},
                },
            ],
            "confidence": {"overall": 0.82},
        },
        validation=ValidationReport(needs_review=True, checks=[]),
        source_engine="granite_vision_3b",
    )

    assert [(item.description, item.net_amount, item.ordinal) for item in candidates] == [
        ("OBEN SPA-1000 SMARTPHONE ADAPTER", 120.32, 1),
        ("OBEN SPA-1000 SMARTPHONE ADAPTER", 20.0, 2),
        ("OBEN CTT-1000 CF TABLETOP TRIPOD", 103.9, 3),
    ]


def test_observation_candidates_suppress_empty_grid_and_duplicate_values() -> None:
    candidates = observation_candidates_from_extraction(
        schema_name="document_observation",
        payload={
            "observations": [
                {
                    "family": "granite_medical_denial.v1",
                    "field_name": "grievance_contact_phone",
                    "value_type": "string",
                    "value": None,
                },
                {
                    "family": "granite_mortgage_escrow_statement.v1",
                    "field_name": "loan_number",
                    "value_type": "string",
                    "value": "123456789",
                },
                {
                    "family": "granite_mortgage_escrow_statement.v1",
                    "field_name": "loan_number",
                    "value_type": "string",
                    "value": "123456789",
                },
                {
                    "family": "granite_generic_kvp.v1",
                    "field_name": "dimensions",
                    "value_type": "object",
                    "value": {"rows": 10, "columns": 10},
                },
                {
                    "family": "granite_generic_kvp.v1",
                    "field_name": "cells",
                    "value_type": "array",
                    "value": [0.0, 0.0, 0.0],
                },
            ]
        },
        validation=ValidationReport(needs_review=True, checks=[]),
    )

    assert [(item.field_name, item.value) for item in candidates] == [("loan_number", "123456789")]
