from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator

from lib.db.migrations import BASELINE_SQL_FILES
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.policy import (
    ALLOWED_SEMANTIC_TYPES,
    SemanticAnnotationValidationError,
    high_quality_required,
    validate_manifest,
)


def test_semantic_annotation_schema_accepts_minimal_valid_manifest() -> None:
    from lib.semantic_annotations.schema import semantic_annotation_manifest_schema

    schema = semantic_annotation_manifest_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(
        {
            "schema_name": "semantic_annotation_manifest",
            "schema_version": "v1",
            "document_type": "medical_eob",
            "pages": [
                {
                    "page_id": "11111111-1111-4111-8111-111111111111",
                    "page_number": 1,
                    "page_role": "claim_summary",
                    "document_type_hint": "medical_eob",
                    "extraction_usefulness": "high",
                    "is_boilerplate": False,
                    "has_structured_targets": True,
                    "ambiguous": False,
                    "escalation_required": False,
                    "escalation_reasons": [],
                    "reason": "Claim summary and responsibility fields are visible.",
                    "confidence": 0.91,
                }
            ],
            "regions": [
                {
                    "semantic_type": "patient_responsibility_summary",
                    "priority": "high",
                    "granite_task": "kvp",
                    "target_schema": "medical_eob",
                    "expected_fields": ["patient_responsibility", "plan_paid"],
                    "grounding": {
                        "kind": "page",
                        "page_id": "11111111-1111-4111-8111-111111111111",
                        "element_id": None,
                        "table_id": None,
                    },
                    "review_required": False,
                    "reason": "Summary block is a high-value extraction target.",
                    "confidence": 0.87,
                }
            ],
            "quality_flags": {
                "needs_high_quality_pass": False,
                "visual_degradation": False,
            },
            "confidence": {"overall": 0.89},
        }
    )


def test_semantic_annotation_schema_rejects_extracted_region_values() -> None:
    from jsonschema import ValidationError

    from lib.semantic_annotations.schema import semantic_annotation_manifest_schema

    manifest = {
        "schema_name": "semantic_annotation_manifest",
        "schema_version": "v1",
        "document_type": "invoice",
        "pages": [],
        "regions": [
            {
                "semantic_type": "billing_summary",
                "priority": "high",
                "granite_task": "kvp",
                "target_schema": "invoice",
                "expected_fields": ["total_amount"],
                "grounding": {
                    "kind": "unmatched_region",
                    "page_id": None,
                    "element_id": None,
                    "table_id": None,
                },
                "review_required": True,
                "reason": "Summary block may contain totals.",
                "confidence": 0.4,
                "value": "$42.00",
            }
        ],
        "quality_flags": {},
        "confidence": {"overall": 0.5},
    }

    with pytest.raises(ValidationError):
        Draft202012Validator(semantic_annotation_manifest_schema()).validate(manifest)


def test_semantic_annotation_schema_uses_vllm_supported_subset() -> None:
    from lib.semantic_annotations.schema import (
        semantic_annotation_manifest_schema,
        semantic_annotation_model_output_schema,
    )

    unsupported_keywords = {"uniqueItems", "oneOf", "anyOf", "allOf"}
    found: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            found.extend(str(key) for key in value if key in unsupported_keywords)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(semantic_annotation_manifest_schema())
    visit(semantic_annotation_model_output_schema())

    assert found == []


def test_semantic_annotation_model_output_schema_bounds_model_generated_arrays() -> None:
    from lib.semantic_annotations.schema import semantic_annotation_model_output_schema

    schema = semantic_annotation_model_output_schema()
    defs = schema["$defs"]

    assert schema["properties"]["pages"]["maxItems"] == 4
    assert schema["properties"]["regions"]["maxItems"] == 6
    assert "confidence" not in schema["required"]
    assert defs["pageAnnotation"]["properties"]["escalation_reasons"]["maxItems"] == 4
    assert defs["regionAnnotation"]["properties"]["expected_fields"]["maxItems"] == 8


def test_semantic_annotation_schemas_include_expanded_qwen4_routing_vocabulary() -> None:
    from lib.semantic_annotations.schema import (
        semantic_annotation_manifest_schema,
        semantic_annotation_model_output_schema,
    )

    for schema in (
        semantic_annotation_manifest_schema(),
        semantic_annotation_model_output_schema(),
    ):
        document_types = schema["properties"]["document_type"]["enum"]
        region_types = schema["$defs"]["regionAnnotation"]["properties"]["semantic_type"]["enum"]
        target_schemas = schema["$defs"]["regionAnnotation"]["properties"]["target_schema"]["enum"]

        assert "retail_order" in document_types
        assert "real_estate_title" in document_types
        assert "mortgage_escrow_statement" in document_types
        assert "financial_dispute_form" in document_types
        assert "generic_form" in document_types
        assert "unsupported_document" in document_types
        assert "retail_order_line_item_table" in region_types
        assert "seller_information_block" in region_types
        assert "escrow_summary" in region_types
        assert "dispute_transaction_table" in region_types
        assert "generic_form_kvp" in region_types
        assert "document_observation" in target_schemas


def test_semantic_manifest_schema_is_not_the_model_generation_schema() -> None:
    from lib.semantic_annotations.schema import (
        semantic_annotation_manifest_schema,
        semantic_annotation_model_output_schema,
    )

    manifest_schema = semantic_annotation_manifest_schema()
    model_schema = semantic_annotation_model_output_schema()

    assert manifest_schema["properties"]["schema_name"]["const"] == "semantic_annotation_manifest"
    assert model_schema["properties"]["schema_name"]["const"] == "semantic_annotation_model_output"
    assert "confidence" in manifest_schema["required"]
    assert "confidence" not in model_schema["required"]
    assert "maxItems" not in manifest_schema["properties"]["pages"]
    assert "maxItems" not in manifest_schema["properties"]["regions"]


def test_semantic_region_db_constraint_covers_policy_semantic_types() -> None:
    migration_name = "080_phase8_5_semantic_type_expansion.sql"
    assert migration_name in BASELINE_SQL_FILES
    migration_sql = (Path(__file__).resolve().parents[3] / "database" / migration_name).read_text(
        encoding="utf-8"
    )

    for semantic_type in sorted(ALLOWED_SEMANTIC_TYPES):
        assert f"'{semantic_type}'" in migration_sql


def _manifest_with_region(region: SemanticRegionAnnotation) -> DocumentSemanticManifest:
    page_id = region.grounding.page_id or uuid4()
    return DocumentSemanticManifest(
        document_id=uuid4(),
        household_id=uuid4(),
        quality_mode="smart",
        profile_name="qwen3-vl-4b-semantic:v1",
        source_engine="qwen3_vl_4b",
        model_name="Qwen/Qwen3-VL-4B-Instruct",
        model_version="test",
        prompt_version="phase8_5-semantic-smart-v2",
        pages=[
            PageSemanticAnnotation(
                page_id=page_id,
                page_number=1,
                page_role="claim_summary",
                document_type_hint="medical_eob",
                extraction_usefulness="high",
                has_structured_targets=True,
                confidence=0.86,
            )
        ],
        regions=[region],
        confidence={"overall": 0.84},
        manifest={"document_type": "medical_eob"},
    )


def _manifest_with_pages(
    *,
    page_ids: list,
    regions: list[SemanticRegionAnnotation],
) -> DocumentSemanticManifest:
    return DocumentSemanticManifest(
        document_id=uuid4(),
        household_id=uuid4(),
        quality_mode="smart",
        profile_name="qwen3-vl-4b-semantic:v1",
        source_engine="qwen3_vl_4b",
        model_name="Qwen/Qwen3-VL-4B-Instruct",
        model_version="test",
        prompt_version="phase8_5-semantic-smart-v2",
        pages=[
            PageSemanticAnnotation(
                page_id=page_id,
                page_number=index + 1,
                page_role="claim_summary",
                document_type_hint="medical_eob",
            )
            for index, page_id in enumerate(page_ids)
        ],
        regions=regions,
        confidence={"overall": 0.84},
        manifest={"document_type": "medical_eob"},
    )


def test_validate_manifest_accepts_docling_grounded_region() -> None:
    element_id = uuid4()
    region = SemanticRegionAnnotation(
        semantic_type="covered_services_line_item_table",
        priority="high",
        granite_task="tables_json",
        target_schema="medical_eob",
        expected_fields=("service_date", "allowed_amount", "patient_responsibility"),
        grounding=SemanticGroundingRef(kind="element", element_id=element_id),
        reason="Docling table-like element contains claim line items.",
        confidence=0.91,
    )

    manifest = _manifest_with_region(region)
    validate_manifest(
        manifest,
        valid_page_ids={manifest.pages[0].page_id},
        valid_element_ids={element_id},
        valid_table_ids=set(),
    )


def test_validate_manifest_requires_exact_page_coverage() -> None:
    first_page = uuid4()
    missing_page = uuid4()
    manifest = _manifest_with_pages(page_ids=[first_page], regions=[])

    with pytest.raises(SemanticAnnotationValidationError, match="page coverage"):
        validate_manifest(
            manifest,
            valid_page_ids={first_page, missing_page},
            valid_element_ids=set(),
            valid_table_ids=set(),
        )


def test_validate_manifest_accepts_distinct_regions_on_same_grounding() -> None:
    page_id = uuid4()
    first = SemanticRegionAnnotation(
        semantic_type="billing_summary",
        priority="high",
        granite_task="kvp",
        target_schema="invoice",
        grounding=SemanticGroundingRef(kind="page", page_id=page_id),
    )
    second = SemanticRegionAnnotation(
        semantic_type="payment_summary",
        priority="medium",
        granite_task="kvp",
        target_schema="invoice",
        grounding=SemanticGroundingRef(kind="page", page_id=page_id),
    )

    validate_manifest(
        _manifest_with_pages(page_ids=[page_id], regions=[first, second]),
        valid_page_ids={page_id},
        valid_element_ids=set(),
        valid_table_ids=set(),
    )


def test_validate_manifest_rejects_exact_duplicate_region_intent() -> None:
    page_id = uuid4()
    first = SemanticRegionAnnotation(
        semantic_type="billing_summary",
        priority="high",
        granite_task="kvp",
        target_schema="invoice",
        expected_fields=("total_amount",),
        grounding=SemanticGroundingRef(kind="page", page_id=page_id),
    )
    second = SemanticRegionAnnotation(
        semantic_type="billing_summary",
        priority="medium",
        granite_task="kvp",
        target_schema="invoice",
        expected_fields=("total_amount",),
        grounding=SemanticGroundingRef(kind="page", page_id=page_id),
    )

    with pytest.raises(SemanticAnnotationValidationError, match="Duplicate"):
        validate_manifest(
            _manifest_with_pages(page_ids=[page_id], regions=[first, second]),
            valid_page_ids={page_id},
            valid_element_ids=set(),
            valid_table_ids=set(),
        )


def test_validate_manifest_rejects_value_like_expected_field_names() -> None:
    page_id = uuid4()
    region = SemanticRegionAnnotation(
        semantic_type="billing_summary",
        priority="high",
        granite_task="kvp",
        target_schema="invoice",
        expected_fields=("invoice.total_amount",),
        grounding=SemanticGroundingRef(kind="page", page_id=page_id),
    )

    with pytest.raises(SemanticAnnotationValidationError, match="expected field"):
        validate_manifest(
            _manifest_with_pages(page_ids=[page_id], regions=[region]),
            valid_page_ids={page_id},
            valid_element_ids=set(),
            valid_table_ids=set(),
        )


def test_validate_manifest_rejects_unknown_granite_task() -> None:
    region = SemanticRegionAnnotation(
        semantic_type="billing_summary",
        priority="high",
        granite_task="made_up_task",
        target_schema="invoice",
        grounding=SemanticGroundingRef(kind="page", page_id=uuid4()),
        review_required=True,
    )

    page_id = region.grounding.page_id
    assert page_id is not None
    with pytest.raises(SemanticAnnotationValidationError, match="granite task"):
        validate_manifest(
            _manifest_with_region(region),
            valid_page_ids={page_id},
            valid_element_ids=set(),
            valid_table_ids=set(),
        )


def test_validate_manifest_rejects_unknown_semantic_type() -> None:
    region = SemanticRegionAnnotation(
        semantic_type="some_new_unreviewed_type",
        priority="medium",
        granite_task="kvp",
        target_schema="receipt",
        grounding=SemanticGroundingRef(kind="page", page_id=uuid4()),
        review_required=True,
    )

    page_id = region.grounding.page_id
    assert page_id is not None
    with pytest.raises(SemanticAnnotationValidationError, match="semantic type"):
        validate_manifest(
            _manifest_with_region(region),
            valid_page_ids={page_id},
            valid_element_ids=set(),
            valid_table_ids=set(),
        )


def test_validate_manifest_requires_unmatched_regions_to_be_review_required() -> None:
    region = SemanticRegionAnnotation(
        semantic_type="unmatched_region",
        priority="low",
        granite_task=None,
        grounding=SemanticGroundingRef(kind="unmatched_region"),
        review_required=False,
        confidence=0.4,
    )

    with pytest.raises(SemanticAnnotationValidationError, match="review-required"):
        validate_manifest(
            _manifest_with_pages(page_ids=[], regions=[region]),
            valid_page_ids=set(),
            valid_element_ids=set(),
            valid_table_ids=set(),
        )


def test_high_quality_policy_triggers_for_failure_low_confidence_and_sensitive_domains() -> None:
    assert high_quality_required(
        validation_failed=True,
        confidence=0.9,
        document_family="invoice",
        quality_flags={},
        user_marked_important=False,
    )
    assert high_quality_required(
        validation_failed=False,
        confidence=0.55,
        document_family="invoice",
        quality_flags={},
        user_marked_important=False,
    )
    assert high_quality_required(
        validation_failed=False,
        confidence=0.88,
        document_family="medical_eob",
        quality_flags={},
        user_marked_important=False,
    )
    assert high_quality_required(
        validation_failed=False,
        confidence=0.88,
        document_family="generic",
        quality_flags={"ocr_quality": "poor"},
        user_marked_important=False,
    )


def test_high_quality_policy_does_not_trigger_for_clean_low_risk_document() -> None:
    assert not high_quality_required(
        validation_failed=False,
        confidence=0.9,
        document_family="generic",
        quality_flags={},
        user_marked_important=False,
    )
