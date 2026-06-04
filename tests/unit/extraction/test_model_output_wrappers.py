from __future__ import annotations

from lib.extraction.model_output_wrappers import unwrap_model_output_payload


def test_model_output_wrapper_unwraps_data_payload_and_preserves_sibling_context() -> None:
    payload, repairs = unwrap_model_output_payload(
        {
            "data": {"line_items": [{"description": "Alignment service"}]},
            "totals": {"total": "$99.00"},
            "confidence": {"overall": 0.82},
        }
    )

    assert payload == {
        "line_items": [{"description": "Alignment service"}],
        "totals": {"total": "$99.00"},
        "confidence": {"overall": 0.82},
    }
    assert repairs == ["unwrapped_data_payload"]
