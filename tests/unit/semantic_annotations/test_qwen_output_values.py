from __future__ import annotations

from lib.semantic_annotations.qwen_output_values import (
    expected_fields_from_json,
    inferred_semantic_type,
    normalized_region_planner_fields,
    select_regions_for_contract,
    target_schema_or_none,
)


def test_qwen_output_values_normalize_fields_and_planner_metadata() -> None:
    assert expected_fields_from_json(
        [
            " Procedure Code ",
            "patient-responsibility",
            "procedure_code",
            "field with punctuation!",
            "ümlaut",
            42,
        ]
    ) == ("procedure_code", "patient_responsibility")

    assert normalized_region_planner_fields(
        {
            "sourceSignal": "Mixed",
            "coverageRole": "Continuation",
            "requiresFullPageImage": False,
            "continuationGroup": "service-lines",
            "mustExtractReason": "Preserve service line evidence.",
            "minExpectedItems": 999,
            "visualBboxHint": {"x1": -5, "y1": "20", "x2": 1200, "y2": 90},
        }
    ) == {
        "source_signal": "mixed",
        "coverage_role": "continuation",
        "requires_full_page_image": False,
        "continuation_group": "service-lines",
        "must_extract_reason": "Preserve service line evidence.",
        "min_expected_items": 500,
        "visual_bbox_hint": {"x1": 0, "y1": 20, "x2": 1000, "y2": 90},
    }

    assert target_schema_or_none("insurance_denial") == "medical_eob"
    assert (
        inferred_semantic_type(
            granite_task="kvp",
            target_schema="medical_eob",
            expected_fields=("request_status", "appeal_deadline"),
        )
        == "denial_or_coverage_decision"
    )
    ranked = select_regions_for_contract(
        [
            {"priority": "low", "granite_task": "kvp", "confidence": 0.99},
            {"priority": "critical", "granite_task": "ignore", "confidence": 0.1},
            {"priority": "high", "granite_task": "tables_json", "confidence": 0.7},
        ]
    )
    assert [region["priority"] for region in ranked] == ["critical", "high", "low"]
