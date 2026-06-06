from __future__ import annotations

from lib.extraction.model_output_wrappers import unwrap_model_output_payload


def test_model_output_wrapper_leaves_object_payload_shape_unchanged() -> None:
    payload, repairs = unwrap_model_output_payload(
        {
            "data": {"line_items": [{"description": "Alignment service"}]},
            "totals": {"total": "$99.00"},
            "confidence": {"overall": 0.82},
        }
    )

    assert payload == {
        "data": {"line_items": [{"description": "Alignment service"}]},
        "totals": {"total": "$99.00"},
        "confidence": {"overall": 0.82},
    }
    assert repairs == []


def test_model_output_wrapper_leaves_normalized_payload_shape_unchanged() -> None:
    payload, repairs = unwrap_model_output_payload(
        {
            "normalized": {"fields": [{"name": "seller", "value": "Jane Seller"}]},
            "confidence": {"overall": 0.82},
        }
    )

    assert payload == {
        "normalized": {"fields": [{"name": "seller", "value": "Jane Seller"}]},
        "confidence": {"overall": 0.82},
    }
    assert repairs == []


def test_model_output_wrapper_drops_non_object_payloads_instead_of_creating_raw_text() -> None:
    payload, repairs = unwrap_model_output_payload("Return only JSON matching the schema")

    assert payload == {}
    assert repairs == ["dropped_non_object_str_model_output_payload"]


def test_model_output_wrapper_drops_list_payloads_instead_of_creating_synthetic_fields() -> None:
    payload, repairs = unwrap_model_output_payload(["seller", "amount", "date"])

    assert payload == {}
    assert repairs == ["dropped_non_object_list_model_output_payload"]
