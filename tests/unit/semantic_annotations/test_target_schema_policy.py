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
