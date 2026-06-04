from __future__ import annotations

from uuid import UUID, uuid4

from lib.semantic_annotations.extraction_plan import GraniteJobSpec, plan_granite_jobs
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


def _generic_form_spec(*, index: int, page_id: UUID) -> GraniteJobSpec:
    return GraniteJobSpec(
        region=SemanticRegionAnnotation(
            semantic_type="generic_form_kvp",
            priority="high",
            granite_task="kvp",
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            target_schema="document_observation",
            expected_fields=(f"field_{index}",),
            metadata={},
        ),
        region_id=uuid4(),
        target_schema="document_observation",
        canonical_target_schema="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        contract_resolution_reason="generic_observation_fallback",
        compatibility_mode="generic",
        extractor_backend="granite_region",
        priority=10 + index,
        ordinal=index,
        schema_fit=SchemaFitDecision(
            target_schema="document_observation",
            requested_target_schema="document_observation",
            evidence_families=("generic_form",),
            document_type_hint="generic_form",
            reason="generic_observation_fallback",
        ),
        metadata={},
    )
