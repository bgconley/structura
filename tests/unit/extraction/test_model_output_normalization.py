from __future__ import annotations

from uuid import uuid4

from lib.extraction.model_output_normalization import (
    normalize_granite_region_output,
    observation_dicts_from_payload,
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
