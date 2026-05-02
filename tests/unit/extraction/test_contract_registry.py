from __future__ import annotations

from uuid import uuid4

from lib.extraction.contract_registry import (
    canonical_target_schema_for,
    resolve_model_output_contract,
)
from lib.extraction.model_output_schemas import model_output_schema_for_task
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef


def test_exact_receipt_contract_resolves_as_exact() -> None:
    resolution = resolve_model_output_contract(
        resolved_document_type="receipt",
        semantic_type="receipt_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        allow_generic_fallback=False,
    )

    assert resolution.schema_name == "granite_receipt_line_items.v1"
    assert resolution.compatibility_mode == "exact"
    assert resolution.exact is True
    assert resolution.review_only is False
    assert resolution.canonical_target_schema == "receipt"


def test_service_record_receipt_like_alias_does_not_change_canonical_target() -> None:
    resolution = resolve_model_output_contract(
        resolved_document_type="service_record",
        semantic_type="receipt_payment_summary",
        granite_task="kvp",
        target_schema="receipt",
        allow_generic_fallback=False,
    )

    assert resolution.schema_name == "granite_receipt_payment_summary.v1"
    assert resolution.compatibility_mode == "compatible_alias"
    assert resolution.exact is False
    assert resolution.review_only is False
    assert resolution.canonical_target_schema == "service_record"


def test_document_observation_contracts_are_review_only() -> None:
    resolution = resolve_model_output_contract(
        resolved_document_type="real_estate_title",
        semantic_type="seller_information_block",
        granite_task="kvp",
        target_schema="document_observation",
        allow_generic_fallback=True,
    )

    assert resolution.schema_name == "granite_real_estate_title_seller_info.v1"
    assert resolution.compatibility_mode == "exact"
    assert resolution.review_only is True
    assert resolution.canonical_target_schema == "document_observation"


def test_generic_fallback_cannot_create_canonical_receipt_contract() -> None:
    resolution = resolve_model_output_contract(
        resolved_document_type="generic",
        semantic_type="generic_form_kvp",
        granite_task="kvp",
        target_schema="receipt",
        allow_generic_fallback=True,
    )

    assert resolution.schema_name is None
    assert resolution.compatibility_mode == "missing"
    assert resolution.reason == "family_schema_incompatible"


def test_model_output_schema_uses_qwen_document_type_over_generic_family_metadata() -> None:
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=uuid4(),
        semantic_type="receipt_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        expected_fields=("line_items",),
        grounding=SemanticGroundingRef(kind="page"),
        metadata={
            "resolved_document_type": "receipt",
            "persisted_document_family": "generic",
        },
    )

    schema = model_output_schema_for_task(schema_name="receipt", semantic_task=task)

    assert schema is not None
    assert schema.name == "granite_receipt_line_items.v1"


def test_receipt_payment_summary_without_planner_metadata_keeps_receipt_contract() -> None:
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=uuid4(),
        semantic_type="payment_summary",
        granite_task="kvp",
        target_schema="receipt",
        expected_fields=("total",),
        grounding=SemanticGroundingRef(kind="page"),
        metadata={},
    )

    schema = model_output_schema_for_task(schema_name="receipt", semantic_task=task)

    assert schema is not None
    assert schema.name == "granite_receipt_payment_summary.v1"


def test_canonical_target_schema_preserves_alias_family() -> None:
    assert (
        canonical_target_schema_for(
            resolved_document_type="retail_order",
            target_schema="receipt",
        )
        == "retail_order"
    )
