from __future__ import annotations

from lib.semantic_annotations.target_schema_policy import preferred_target_schema


def test_generic_form_semantic_regions_route_to_observation_schema() -> None:
    assert (
        preferred_target_schema(
            document_family="other",
            document_metadata={},
            document_type_hint="generic_form",
            semantic_type="generic_form_kvp",
            model_target_schema="document_observation",
        )
        == "document_observation"
    )


def test_title_and_escrow_semantic_regions_do_not_masquerade_as_invoice_or_eob() -> None:
    assert (
        preferred_target_schema(
            document_family="financial",
            document_metadata={},
            document_type_hint="real_estate_title",
            semantic_type="seller_information_block",
            model_target_schema=None,
        )
        == "document_observation"
    )
    assert (
        preferred_target_schema(
            document_family="financial",
            document_metadata={},
            document_type_hint="mortgage_escrow_statement",
            semantic_type="escrow_summary",
            model_target_schema=None,
        )
        == "document_observation"
    )


def test_qwen_document_type_hint_beats_phase4_classifier_hint() -> None:
    assert (
        preferred_target_schema(
            document_family="medical_eob",
            document_metadata={"phase4": {"classification": {"family": "medical_eob"}}},
            document_type_hint="receipt",
            semantic_type=None,
            model_target_schema=None,
        )
        == "receipt"
    )


def test_qwen_observation_document_type_beats_bad_region_schema_hint() -> None:
    assert (
        preferred_target_schema(
            document_family="receipt",
            document_metadata={"phase4": {"classification": {"family": "receipt"}}},
            document_type_hint="real_estate_title",
            semantic_type="receipt_line_item_table",
            model_target_schema="receipt",
        )
        == "document_observation"
    )
