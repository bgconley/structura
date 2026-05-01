from __future__ import annotations

from uuid import uuid4

from lib.extraction.model_output_normalization import (
    normalize_granite_region_output,
    observation_dicts_from_payload,
)
from lib.extraction.models import ValidationReport
from lib.extraction.normalization import (
    line_item_candidates_from_extraction,
    observation_candidates_from_extraction,
)
from lib.extraction.validators import validate_extraction_payload


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
