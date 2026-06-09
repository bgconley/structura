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
from tests.unit.extraction.model_output_contract_fixtures import confidence as _confidence
from tests.unit.extraction.model_output_contract_fixtures import generic_field as _generic_field
from tests.unit.extraction.model_output_contract_fixtures import (
    invoice_line_item as _invoice_line_item,
)
from tests.unit.extraction.model_output_contract_fixtures import invoice_totals as _invoice_totals
from tests.unit.extraction.model_output_contract_fixtures import (
    receipt_line_item as _receipt_line_item,
)
from tests.unit.extraction.model_output_contract_fixtures import receipt_totals as _receipt_totals
from tests.unit.extraction.model_output_contract_fixtures import (
    receipt_payment_payload as _receipt_payment_payload,
)
from tests.unit.extraction.model_output_contract_fixtures import (
    seller_info_payload as _seller_info_payload,
)


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
        payload=_seller_info_payload(
            seller_name="Brennan Conley",
            property_address="123 Main St",
        ),
    )

    assert normalized["schema_name"] == "document_observation"
    assert [item["field_name"] for item in normalized["observations"]] == [
        "seller_name",
        "property_address",
    ]
    assert metadata["mapper"] == "granite_real_estate_title_seller_info.v1"
    assert observation_dicts_from_payload(normalized)[0]["value"] == "Brennan Conley"


def test_direct_observation_contract_rejects_unknown_top_level_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_real_estate_title_seller_info.v1",
        payload=_seller_info_payload(
            seller_name="Brennan Conley",
            notary_name="Jane Notary",
        ),
    )

    observations = observation_dicts_from_payload(normalized)
    assert observations == []
    assert metadata["rejected_fields"] == ["notary_name"]
    assert "model_output_contract_validation_failed" in metadata["repairs"]


def test_direct_observation_contract_reports_fields_array_as_rejected() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_real_estate_title_seller_info.v1",
        payload={
            "fields": [{"name": "seller_name", "value": "Jane Seller"}],
            "confidence": {"overall": 0.74},
        },
    )

    assert normalized["observations"] == []
    assert metadata["rejected_fields"] == ["fields"]


def test_generic_kvp_contract_rejects_flat_top_level_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "seller_notes": "Jane Seller",
            "confidence": _confidence(0.61),
        },
    )

    assert normalized["observations"] == []
    assert metadata["repairs"] == ["model_output_contract_validation_failed"]
    assert metadata["rejected_fields"] == ["seller_notes"]
    assert "$: 'fields' is a required property" in metadata["model_output_contract_errors"]


def test_uncontracted_document_observation_rejects_arbitrary_flat_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name=None,
        payload={
            "seller_notes": "Jane Seller",
            "confidence": {"overall": 0.61},
        },
    )

    assert normalized["observations"] == []
    assert metadata["mapper"] is None
    assert metadata["repairs"] == ["uncontracted_observation_payload_rejected"]
    assert metadata["rejected_fields"] == ["seller_notes"]


def test_legacy_candidate_creation_rejects_qwen_value_sources() -> None:
    document_id = uuid4()
    evidence = [{"page_number": 1, "source_engine": "qwen3_vl_8b", "source_text": "$42.00"}]

    field_candidates = field_candidates_from_extraction(
        document_id=document_id,
        schema_name="invoice",
        payload={
            "schema_name": "invoice",
            "invoice": {"invoice_number": "INV-42", "evidence": evidence},
            "totals": {
                "total": {"amount": 42.0, "currency": "USD"},
                "evidence": evidence,
            },
            "confidence": {"overall": 0.75},
        },
        validation=ValidationReport(needs_review=False, checks=[]),
        source_engine="qwen3_vl_8b",
    )
    line_item_candidates = line_item_candidates_from_extraction(
        schema_name="invoice",
        payload={
            "schema_name": "invoice",
            "line_items": [
                {
                    "description": "Qwen value",
                    "amount": {"amount": 42.0, "currency": "USD"},
                    "evidence": evidence,
                }
            ],
            "confidence": {"overall": 0.75},
        },
        validation=ValidationReport(needs_review=False, checks=[]),
        source_engine="qwen3_vl_8b",
    )
    observation_candidates = observation_candidates_from_extraction(
        schema_name="document_observation",
        payload={
            "schema_name": "document_observation",
            "observations": [
                {
                    "field_name": "claimed_total",
                    "value_type": "string",
                    "value": "$42.00",
                    "evidence": evidence,
                }
            ],
        },
        validation=ValidationReport(needs_review=False, checks=[]),
        source_engine="qwen3_vl_8b",
    )

    assert field_candidates == []
    assert line_item_candidates == []
    assert observation_candidates == []


def test_review_only_receipt_like_output_defers_broad_observations() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "fields": [
                _generic_field("total_amount", "$42.00"),
                _generic_field("payment_method", "AMEX CREDIT"),
            ],
            "confidence": _confidence(),
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


def test_review_only_receipt_like_output_defers_when_resolved_as_receipt() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "fields": [
                _generic_field("subtotal", "$20.00"),
                _generic_field("tax", "$1.60"),
                _generic_field("total_amount", "$21.60"),
                _generic_field("payment_method", "CARD"),
            ],
            "confidence": _confidence(),
        },
        semantic_type="receipt_payment_summary",
        target_schema="document_observation",
        resolved_document_type="receipt",
    )

    assert normalized["schema_name"] == "document_observation"
    assert normalized["observations"] == []
    assert normalized["metadata"]["deferred_observation_count"] == 4
    assert metadata["deferred_observation_count"] == 4
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
        payload={
            "line_items": [
                _invoice_line_item(
                    description="Alignment service",
                    amount="$99.00",
                    table_id=str(table_id),
                    page_number=3,
                )
            ],
            "totals": _invoice_totals(),
            "confidence": _confidence(table_structure=0.8),
        },
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


def test_invoice_line_item_contract_drops_off_contract_item_keys() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "line_items": [
                _invoice_line_item(
                    description="Alignment service",
                    service_cost="$99.00",
                ),
                _invoice_line_item(
                    service_type="Tire mounting",
                    amount="$42.00",
                ),
            ],
            "totals": _invoice_totals(),
            "confidence": _confidence(table_structure=0.8),
        },
    )

    assert normalized["line_items"] == []


def test_invoice_line_item_contract_drops_top_level_alias_key() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "invoice_line_items": [
                {
                    "description": "Alignment service",
                    "amount": "$99.00",
                }
            ]
        },
    )

    assert normalized["line_items"] == []
    assert metadata["rejected_fields"] == ["invoice_line_items"]


def test_receipt_line_item_contract_drops_service_record_item_aliases() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        payload={
            "line_items": [
                _receipt_line_item(
                    service_description="Battery replacement",
                    line_total="$44.00",
                )
            ],
            "totals": _receipt_totals(),
            "confidence": _confidence(table_structure=0.8),
        },
    )

    assert normalized["line_items"] == []


def test_authoritative_docling_table_rejects_line_items_without_row_identity() -> None:
    document_id = uuid4()
    table_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_invoice_line_items.v1",
        payload={
            "line_items": [
                _invoice_line_item(
                    description="Grounded row",
                    row_index=1,
                    table_id=str(table_id),
                    page_number=2,
                    amount="$99.00",
                ),
                _invoice_line_item(
                    description="Invented row",
                    amount="$12.00",
                    table_id=str(table_id),
                    page_number=2,
                ),
            ],
            "totals": _invoice_totals(),
            "confidence": _confidence(0.81, table_structure=0.8),
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
        payload=_receipt_payment_payload(
            merchant_name="Coffee Shop",
            transaction_date="2026-05-01",
            subtotal="$4.25",
            tax="$0.40",
            total="$4.65",
        ),
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
    assert has_concrete_evidence(normalized["evidence"]) is True

    candidates = field_candidates_from_extraction(
        document_id=document_id,
        schema_name="receipt",
        payload=normalized,
        validation=ValidationReport(needs_review=True, checks=[]),
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    assert candidates == []
    assert metadata["deferred_payment_summary_fields"] == ["subtotal", "tax", "total"]
    assert metadata["deferred_payment_summary_identity_fields"] == [
        "merchant_name",
        "transaction_date",
    ]


def test_receipt_payment_summary_defers_unanchored_money_candidates_for_repeatability() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload=_receipt_payment_payload(
            merchant_name="Coffee Shop",
            transaction_date="2026-05-01",
            subtotal="$4.25",
            tax="$0.40",
            total="$4.65",
        ),
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

    assert candidates == []
    assert metadata["deferred_payment_summary_fields"] == ["subtotal", "tax", "total"]
    assert metadata["deferred_payment_summary_identity_fields"] == [
        "merchant_name",
        "transaction_date",
    ]


def test_receipt_payment_summary_defers_page_identity_when_money_is_deferred() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload=_receipt_payment_payload(
            merchant_name="Amtra",
            transaction_date="2025-09-09",
            subtotal="$12.00",
            tip="$2.00",
            total="$14.00",
        ),
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

    assert candidates == []
    assert metadata["deferred_payment_summary_fields"] == ["subtotal", "tip", "total"]
    assert metadata["deferred_payment_summary_identity_fields"] == [
        "merchant_name",
        "transaction_date",
    ]
    assert "deferred_payment_summary_identity_for_page_summary" in metadata["repairs"]


def test_receipt_payment_summary_defers_page_identity_without_amount_signal() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload=_receipt_payment_payload(
            merchant_name="Amtra",
            transaction_date="2025-09-09",
            total=None,
        ),
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

    assert candidates == []
    assert metadata["deferred_payment_summary_identity_fields"] == [
        "merchant_name",
        "transaction_date",
    ]
    assert "deferred_payment_summary_identity_without_amount_signal" in metadata["repairs"]


def test_receipt_payment_summary_persists_region_envelope_projection() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    page_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload=_receipt_payment_payload(
            merchant_name="Coffee Shop",
            transaction_date="2026-05-01",
            subtotal="$4.25",
            tax="$0.40",
            total="$4.65",
            confidence=_confidence(0.83),
        ),
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
    assert envelope["facts"] == []
    assert metadata["deferred_payment_summary_fields"] == ["subtotal", "tax", "total"]
    assert metadata["deferred_payment_summary_identity_fields"] == [
        "merchant_name",
        "transaction_date",
    ]


def test_receipt_payment_summary_parses_model_datetime_before_candidate_insert() -> None:
    document_id = uuid4()

    normalized, _metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        payload=_receipt_payment_payload(
            merchant_name="Coffee Shop",
            transaction_date="10-Sep-2025 12:17:38P",
            total="$4.65",
        ),
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_annotation_id=uuid4(),
            semantic_region_id=uuid4(),
            page_id=uuid4(),
            page_number=1,
            bbox=[10, 20, 200, 80],
            bbox_basis="model_region",
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
            "confidence": _confidence(),
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
            "confidence": _confidence(),
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
                    "name": None,
                    "phone": "555-0100",
                    "fax": None,
                    "address": None,
                    "url": None,
                    "deadline": None,
                    "source_text": "Appeals: 555-0100",
                    "confidence": 0.8,
                }
            ],
            "service_lines": [],
            "warnings": [],
            "confidence": _confidence(),
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
                    "contact_type": None,
                    "name": "Grievances and Appeals",
                    "phone": "1-800-365-0609",
                    "fax": None,
                    "address": None,
                    "url": None,
                    "deadline": None,
                    "source_text": "Grievances and Appeals 1-800-365-0609",
                    "confidence": 0.8,
                }
            ],
            "service_lines": [],
            "warnings": [],
            "confidence": _confidence(),
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


def test_generic_kvp_mapper_rejects_flat_prompt_echo_payload() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "properties": {"seller_name": {"type": "string"}},
            "instructions": "Return only JSON matching this schema",
            "seller_name": "Jane Seller",
            "confidence": _confidence(),
        },
    )

    assert observation_dicts_from_payload(normalized) == []
    assert metadata["repairs"] == ["model_output_contract_validation_failed"]
    assert metadata["rejected_fields"] == [
        "instructions",
        "properties",
        "seller_name",
    ]
    assert "$: 'fields' is a required property" in metadata["model_output_contract_errors"]


def test_receipt_line_item_model_output_maps_to_canonical_receipt_lines() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        payload={
            "line_items": [
                _receipt_line_item(
                    description="USB-C cable",
                    quantity="2",
                    unit_price="$9.99",
                    amount="$19.98",
                )
            ],
            "totals": _receipt_totals(total="$21.63"),
            "confidence": _confidence(0.82, table_structure=0.8),
        },
    )

    assert normalized["schema_name"] == "receipt"
    assert normalized["line_items"][0]["description"] == "USB-C cable"
    assert normalized["line_items"][0]["amount"] == {"amount": 19.98, "currency": "USD"}
    assert normalized["transaction"]["total"] == {"amount": 21.63, "currency": "USD"}
    assert metadata["mapper"] == "granite_receipt_line_items.v1"


def test_service_record_flat_output_is_rejected_as_off_contract_shape() -> None:
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
    assert normalized["line_items"] == []
    assert metadata["rejected_fields"] == [
        "labor_operation",
        "line_total",
        "part_number",
        "quantity",
        "service_description",
        "unit_price",
    ]
    assert metadata["mapper"] == "granite_service_record_line_items.v1"


def test_wrapped_data_payload_is_not_mined_for_invoice_line_items() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
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
            "totals": _invoice_totals(total={"amount": 99.00, "currency": "USD"}),
            "confidence": _confidence(table_structure=0.8),
        },
    )

    assert normalized["line_items"] == []
    assert "totals" not in normalized
    assert metadata["rejected_fields"] == ["data"]
    assert (
        "$.totals.total: {'amount': 99.0, 'currency': 'USD'} is not of type "
        "'number', 'string', 'null'"
    ) in metadata["model_output_contract_errors"]
    assert "$: 'line_items' is a required property" in metadata["model_output_contract_errors"]


def test_observation_payload_with_type_object_and_fields_is_not_schema_echo() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "type": "object",
            "fields": [_generic_field("seller_name", "Jane Seller")],
            "confidence": _confidence(),
        },
    )

    assert "schema_echo_rejected" not in metadata["repairs"]
    assert observation_dicts_from_payload(normalized) == []
    assert metadata["rejected_fields"] == ["type"]
    assert "model_output_contract_validation_failed" in metadata["repairs"]


def test_observation_source_text_over_schema_limit_fails_closed() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        payload={
            "fields": [
                {
                    "name": "seller_notes",
                    "value": "Jane Seller",
                    "source_text": "x" * 700,
                    "confidence": 0.61,
                }
            ],
            "confidence": _confidence(0.61),
        },
    )
    report = validate_extraction_payload("document_observation", normalized)

    assert report.checks[0]["status"] == "passed"
    observations = observation_dicts_from_payload(normalized)
    assert observations == []
    assert any(
        error.startswith("$.fields[0].source_text: ") and error.endswith("is too long")
        for error in metadata["model_output_contract_errors"]
    )


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
