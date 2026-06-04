from __future__ import annotations

from uuid import UUID, uuid4

from lib.semantic_annotations.extraction_plan import (
    GraniteExtractionPlan,
    GraniteJobSpec,
    plan_granite_jobs,
)
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


def test_persist_extraction_plan_classifies_dropped_task_reasons() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    page_id = uuid4()
    plan_id = uuid4()
    task_ids = [uuid4(), uuid4(), uuid4()]
    cursor_rows: list[dict[str, object]] = [{"id": plan_id}]
    for task_id in task_ids:
        cursor_rows.append({"id": task_id})
    cursor = RecordingCursor(rows=cursor_rows)
    missing_contract = _spec(
        page_id=page_id,
        region_id=uuid4(),
        model_output_schema_name=" ",
        contract_resolution_reason="missing_contract",
        compatibility_mode="missing",
    )
    missing_grounding = _spec(
        page_id=None,
        region_id=uuid4(),
        grounding=SemanticGroundingRef(kind="page"),
    )
    incompatible = _spec(
        page_id=page_id,
        region_id=uuid4(),
        contract_resolution_reason="family_schema_incompatible",
        compatibility_mode="incompatible_family",
    )
    plan = plan_granite_jobs(
        [missing_contract, missing_grounding, incompatible],
        quality_mode="smart",
    )

    persist_extraction_plan_with_cursor(
        cursor,
        document_id=document_id,
        semantic_annotation_id=annotation_id,
        manifest_result=SemanticAnnotationResult(
            manifest=_manifest(
                document_id=document_id,
                page_id=page_id,
                regions=[
                    missing_contract.region,
                    missing_grounding.region,
                    incompatible.region,
                ],
            )
        ),
        plan=plan,
        run_id="phase85-20260604-smoke-001",
    )

    plan_params = next(
        params for sql, params in cursor.calls if "INSERT INTO semantic_extraction_plans" in sql
    )
    assert plan_params[6:13] == (0, 3, 0, 1, 1, 1, 0)
    task_params = [
        params
        for sql, params in cursor.calls
        if "INSERT INTO semantic_extraction_plan_tasks" in sql
    ]
    assert [(params[15], params[16]) for params in task_params] == [
        ("skipped_missing_contract", "missing_contract"),
        ("skipped_missing_grounding", "missing_grounding"),
        ("skipped_incompatible_schema", "incompatible_schema"),
    ]


def test_persist_extraction_plan_records_suppressed_duplicate_tasks() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    page_id = uuid4()
    plan_id = uuid4()
    task_ids = [uuid4(), uuid4()]
    cursor_rows: list[dict[str, object]] = [{"id": plan_id}]
    for task_id in task_ids:
        cursor_rows.append({"id": task_id})
    cursor = RecordingCursor(rows=cursor_rows)
    selected = _spec(page_id=page_id, region_id=uuid4())
    duplicate = _spec(
        page_id=page_id,
        region_id=uuid4(),
        priority=selected.priority + 10,
        ordinal=selected.ordinal + 1,
    )
    plan = plan_granite_jobs([selected, duplicate], quality_mode="smart")

    persisted = persist_extraction_plan_with_cursor(
        cursor,
        document_id=document_id,
        semantic_annotation_id=annotation_id,
        manifest_result=SemanticAnnotationResult(
            manifest=_manifest(
                document_id=document_id,
                page_id=page_id,
                regions=[selected.region, duplicate.region],
            )
        ),
        plan=plan,
        run_id="phase85-20260604-smoke-001",
    )

    assert persisted.selected_task_ids == {selected.region_id: task_ids[0]}
    plan_params = next(
        params for sql, params in cursor.calls if "INSERT INTO semantic_extraction_plans" in sql
    )
    assert plan_params[6:13] == (1, 1, 0, 0, 0, 0, 1)
    task_params = [
        params
        for sql, params in cursor.calls
        if "INSERT INTO semantic_extraction_plan_tasks" in sql
    ]
    assert [(params[15], params[16]) for params in task_params] == [
        ("selected", None),
        ("suppressed_duplicate", "duplicate_suppressed"),
    ]


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


def _spec(
    *,
    page_id: UUID | None,
    region_id: UUID,
    grounding: SemanticGroundingRef | None = None,
    model_output_schema_name: str = "granite_receipt_line_items.v1",
    contract_resolution_reason: str = "exact_contract",
    compatibility_mode: str | None = "exact",
    priority: int = 20,
    ordinal: int = 0,
) -> GraniteJobSpec:
    return GraniteJobSpec(
        region=SemanticRegionAnnotation(
            semantic_type="receipt_line_item_table",
            priority="high",
            granite_task="tables_json",
            grounding=grounding or SemanticGroundingRef(kind="page", page_id=page_id),
            expected_fields=("line_items",),
            metadata={},
        ),
        region_id=region_id,
        target_schema="receipt",
        canonical_target_schema="receipt",
        model_output_schema_name=model_output_schema_name,
        contract_resolution_reason=contract_resolution_reason,
        compatibility_mode=compatibility_mode,
        extractor_backend="granite_region",
        priority=priority,
        ordinal=ordinal,
        schema_fit=SchemaFitDecision(
            target_schema="receipt",
            requested_target_schema="receipt",
            evidence_families=("receipt",),
            document_type_hint="receipt",
            reason="docling_anchor_fit",
        ),
        metadata={"resolved_document_type": "receipt"},
    )
