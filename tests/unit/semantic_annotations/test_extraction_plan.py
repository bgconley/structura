from __future__ import annotations

from uuid import UUID, uuid4

from lib.semantic_annotations.extraction_plan import (
    GraniteJobSpec,
    dropped_task_status_and_reason,
    plan_granite_jobs,
)
from lib.semantic_annotations.models import SemanticGroundingRef, SemanticRegionAnnotation
from lib.semantic_annotations.schema_fit import SchemaFitDecision


def test_smart_granite_plan_limits_selected_tasks_per_page() -> None:
    page_id = uuid4()
    specs = [_generic_form_spec(index=index, page_id=page_id) for index in range(6)]

    plan = plan_granite_jobs(specs, quality_mode="smart")

    assert len(plan.selected) == 3
    assert len(plan.dropped) == 3
    assert all(spec.region.grounding.page_id == page_id for spec in plan.selected)
    metadata = plan.to_metadata()
    assert metadata["maxTasksPerDocumentPolicy"] == 6
    assert metadata["maxTasksPerPagePolicy"] == 3
    assert metadata["selectedTaskCountByPage"] == {str(page_id): 3}


def test_smart_granite_plan_prefers_summary_over_extra_docling_tables_on_same_page() -> None:
    page_id = uuid4()
    table_specs = [
        _generic_form_spec(
            index=index,
            page_id=page_id,
            grounding=SemanticGroundingRef(kind="table", page_id=page_id, table_id=uuid4()),
            metadata={"region_source": "docling_structural"},
            priority=30 + index,
        )
        for index in range(3)
    ]
    summary = _generic_form_spec(
        index=3,
        page_id=page_id,
        semantic_type="escrow_summary",
        granite_task="kvp",
        expected_fields=("loan_number", "payment_amount"),
        model_output_schema_name="granite_mortgage_escrow_statement.v1",
        compatibility_mode="exact",
        contract_resolution_reason="exact_contract",
        priority=28,
    )

    plan = plan_granite_jobs([*table_specs, summary], quality_mode="smart")

    selected_region_ids = {spec.region_id for spec in plan.selected}
    dropped_region_ids = {spec.region_id for spec in plan.dropped}
    assert len(plan.selected) == 3
    assert summary.region_id in selected_region_ids
    assert sum(spec.region_id in selected_region_ids for spec in table_specs) == 2
    assert sum(spec.region_id in dropped_region_ids for spec in table_specs) == 1
    assert plan.to_metadata()["selectedTaskCountByPage"] == {str(page_id): 3}


def test_granite_plan_drops_specs_without_model_output_contract() -> None:
    page_id = uuid4()
    spec = _generic_form_spec(index=0, page_id=page_id, model_output_schema_name=" ")

    plan = plan_granite_jobs([spec], quality_mode="smart")

    assert plan.selected == ()
    assert plan.dropped == (spec,)
    assert plan.warnings == (f"granite_plan_missing_contract:{spec.region_id}",)
    metadata = plan.to_metadata()
    assert metadata["selectedCount"] == 0
    assert metadata["safeSkipCount"] == 1
    assert metadata["warnings"] == [f"granite_plan_missing_contract:{spec.region_id}"]


def test_granite_plan_drops_specs_without_concrete_grounding() -> None:
    spec = _generic_form_spec(
        index=0,
        page_id=None,
        grounding=SemanticGroundingRef(kind="page"),
    )

    plan = plan_granite_jobs([spec], quality_mode="smart")

    assert plan.selected == ()
    assert plan.dropped == (spec,)
    assert plan.warnings == (f"granite_plan_missing_grounding:{spec.region_id}",)


def test_granite_plan_drops_incompatible_specs() -> None:
    page_id = uuid4()
    spec = _generic_form_spec(
        index=0,
        page_id=page_id,
        compatibility_mode="incompatible_family",
        contract_resolution_reason="family_schema_incompatible",
    )

    plan = plan_granite_jobs([spec], quality_mode="smart")

    assert plan.selected == ()
    assert plan.dropped == (spec,)
    assert plan.warnings == (f"granite_plan_incompatible_schema:{spec.region_id}",)


def test_granite_plan_records_suppressed_duplicate_specs() -> None:
    page_id = uuid4()
    selected = _generic_form_spec(index=0, page_id=page_id)
    duplicate = _generic_form_spec(
        index=0,
        page_id=page_id,
        priority=selected.priority + 10,
        ordinal=selected.ordinal + 1,
    )

    plan = plan_granite_jobs([selected, duplicate], quality_mode="smart")

    assert [spec.region_id for spec in plan.selected] == [selected.region_id]
    assert [spec.region_id for spec in plan.dropped] == [duplicate.region_id]
    assert plan.summary_counts()["duplicate_suppressed_count"] == 1
    assert plan.to_metadata()["duplicateSuppressedCount"] == 1
    assert plan.warnings == (f"granite_plan_duplicate_suppressed:{duplicate.region_id}",)
    assert dropped_task_status_and_reason(plan.dropped[0]) == (
        "suppressed_duplicate",
        "duplicate_suppressed",
    )


def test_granite_plan_prefers_exact_contracts_over_generic_review_fallbacks() -> None:
    exact_specs = [
        _generic_form_spec(
            index=index,
            page_id=uuid4(),
            semantic_type="denial_or_coverage_decision",
            target_schema="medical_eob",
            canonical_target_schema="medical_eob",
            model_output_schema_name="granite_healthcare_coverage_decision.v1",
            compatibility_mode="exact",
            contract_resolution_reason="exact_contract",
            priority=40,
        )
        for index in range(6)
    ]
    generic_review_only = _generic_form_spec(
        index=99,
        page_id=uuid4(),
        semantic_type="generic_form_kvp",
        target_schema="document_observation",
        canonical_target_schema="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        compatibility_mode="generic_review_only",
        contract_resolution_reason="generic_review_only_fallback",
        priority=1,
        metadata={"coverage_role": "primary"},
    )

    plan = plan_granite_jobs([generic_review_only, *exact_specs], quality_mode="smart")

    selected_region_ids = {spec.region_id for spec in plan.selected}
    assert generic_review_only.region_id not in selected_region_ids
    assert selected_region_ids == {spec.region_id for spec in exact_specs}
    assert [spec.region_id for spec in plan.dropped] == [generic_review_only.region_id]


def _generic_form_spec(
    *,
    index: int,
    page_id: UUID | None,
    grounding: SemanticGroundingRef | None = None,
    semantic_type: str = "generic_form_kvp",
    granite_task: str = "kvp",
    target_schema: str = "document_observation",
    canonical_target_schema: str = "document_observation",
    expected_fields: tuple[str, ...] | None = None,
    model_output_schema_name: str = "granite_generic_kvp.v1",
    compatibility_mode: str | None = "generic",
    contract_resolution_reason: str = "generic_observation_fallback",
    priority: int | None = None,
    ordinal: int | None = None,
    metadata: dict[str, object] | None = None,
) -> GraniteJobSpec:
    return GraniteJobSpec(
        region=SemanticRegionAnnotation(
            semantic_type=semantic_type,
            priority="high",
            granite_task=granite_task,
            grounding=grounding or SemanticGroundingRef(kind="page", page_id=page_id),
            target_schema=target_schema,
            expected_fields=expected_fields or (f"field_{index}",),
            metadata=metadata or {},
        ),
        region_id=uuid4(),
        target_schema=target_schema,
        canonical_target_schema=canonical_target_schema,
        model_output_schema_name=model_output_schema_name,
        contract_resolution_reason=contract_resolution_reason,
        compatibility_mode=compatibility_mode,
        extractor_backend="granite_region",
        priority=priority if priority is not None else 10 + index,
        ordinal=ordinal if ordinal is not None else index,
        schema_fit=SchemaFitDecision(
            target_schema=target_schema,
            requested_target_schema=target_schema,
            evidence_families=("generic_form",),
            document_type_hint="generic_form",
            reason="generic_observation_fallback",
        ),
        metadata={},
    )


def test_continuation_line_item_regions_are_rescued_from_fanout_budgets() -> None:
    pages = [uuid4() for _ in range(7)]
    continuation_specs = [
        _generic_form_spec(
            index=index,
            page_id=page_id,
            semantic_type="invoice_line_item_table",
            granite_task="tables_json",
            target_schema="invoice",
            canonical_target_schema="invoice",
            model_output_schema_name="granite_invoice_line_items.v1",
            compatibility_mode="exact",
            contract_resolution_reason="exact_contract",
            metadata={
                "continuation_group": "service_lines",
                "must_extract_reason": "line_item_table",
            },
        )
        for index, page_id in enumerate(pages, start=1)
    ]
    summary_spec = _generic_form_spec(
        index=99,
        page_id=pages[0],
        semantic_type="payment_summary",
        granite_task="kvp",
        target_schema="invoice",
        canonical_target_schema="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        compatibility_mode="exact",
        contract_resolution_reason="exact_contract",
    )

    plan = plan_granite_jobs([*continuation_specs, summary_spec], quality_mode="smart")

    selected_region_ids = {spec.region_id for spec in plan.selected}
    for spec in continuation_specs:
        assert spec.region_id in selected_region_ids
    assert not any(
        warning.startswith("dropped_must_extract_target:invoice_line_item_table")
        for warning in plan.warnings
    )
