from __future__ import annotations

from uuid import UUID, uuid4

from lib.semantic_annotations.extraction_plan import GraniteExtractionPlan, GraniteJobSpec
from lib.semantic_annotations.extraction_plan_repository import (
    persist_extraction_plan_with_cursor,
)
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)
from lib.semantic_annotations.schema_fit import SchemaFitDecision


def test_persist_extraction_plan_records_summary_and_task_lineage() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    page_id = uuid4()
    region_id = uuid4()
    plan_id = uuid4()
    task_id = uuid4()
    cursor = RecordingCursor(rows=[{"id": plan_id}, {"id": task_id}])
    spec = GraniteJobSpec(
        region=SemanticRegionAnnotation(
            semantic_type="receipt_line_item_table",
            priority="high",
            granite_task="tables_json",
            grounding=SemanticGroundingRef(kind="page", page_id=page_id),
            expected_fields=("line_items",),
            metadata={},
        ),
        region_id=region_id,
        target_schema="receipt",
        canonical_target_schema="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        contract_resolution_reason="exact_contract",
        compatibility_mode="exact",
        extractor_backend="granite_region",
        priority=20,
        ordinal=0,
        schema_fit=SchemaFitDecision(
            target_schema="receipt",
            requested_target_schema="receipt",
            evidence_families=("receipt",),
            document_type_hint="receipt",
            reason="docling_anchor_fit",
        ),
        metadata={"resolved_document_type": "receipt"},
    )
    plan = GraniteExtractionPlan(
        selected=(spec,),
        dropped=(),
        warnings=(),
        bucket_counts={"line_item": 1},
    )

    persisted = persist_extraction_plan_with_cursor(
        cursor,
        document_id=document_id,
        semantic_annotation_id=annotation_id,
        manifest_result=SemanticAnnotationResult(
            manifest=_manifest(
                document_id=document_id,
                page_id=page_id,
                regions=[spec.region],
            )
        ),
        plan=plan,
        run_id="phase85-20260604-smoke-001",
    )

    assert persisted.plan_id == plan_id
    assert persisted.selected_task_ids == {region_id: task_id}
    assert any("INSERT INTO semantic_extraction_plans" in sql for sql, _ in cursor.calls)
    plan_call = next(
        params for sql, params in cursor.calls if "INSERT INTO semantic_extraction_plans" in sql
    )
    assert "phase85-20260604-smoke-001" in plan_call
    task_call = next(
        (sql, params)
        for sql, params in cursor.calls
        if "INSERT INTO semantic_extraction_plan_tasks" in sql
    )
    task_sql, task_params = task_call
    assert "page_number" in task_sql
    assert "COALESCE(psa.page_number, dp.page_number" in task_sql
    assert "LEFT JOIN page_semantic_annotations psa" in task_sql
    assert "granite_receipt_line_items.v1" in task_params
    assert "exact_contract" in task_params


class RecordingCursor:
    def __init__(self, *, rows: list[dict[str, object]]) -> None:
        self.rows = list(rows)
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))

    def fetchone(self) -> dict[str, object] | None:
        return self.rows.pop(0) if self.rows else None


def _manifest(
    *,
    document_id: UUID,
    page_id: UUID,
    regions: list[SemanticRegionAnnotation],
) -> DocumentSemanticManifest:
    return DocumentSemanticManifest(
        document_id=document_id,
        household_id=uuid4(),
        quality_mode="smart",
        profile_name="qwen3-vl-8b-fp8-semantic:v1",
        source_engine="qwen3_vl_8b",
        model_name="Qwen/Qwen3-VL-8B-Instruct-FP8",
        model_version="v1",
        prompt_version="phase8_5-semantic-smart-v3",
        pages=[
            PageSemanticAnnotation(
                page_id=page_id,
                page_number=1,
                page_role="line_items",
            )
        ],
        regions=regions,
        confidence={"overall": 0.9},
        manifest={"document_type": "receipt"},
    )
