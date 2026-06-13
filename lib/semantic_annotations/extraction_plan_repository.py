from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.model_runtime.reliability_versions import PLANNER_VERSION
from lib.semantic_annotations.extraction_plan import (
    GraniteExtractionPlan,
    GraniteJobSpec,
    dropped_task_status_and_reason,
)
from lib.semantic_annotations.models import SemanticAnnotationResult


@dataclass(frozen=True)
class PersistedExtractionPlan:
    plan_id: UUID
    selected_task_ids: dict[UUID, UUID]


@dataclass(frozen=True)
class PlannedExtractionTask:
    plan_id: UUID
    plan_task_id: UUID
    semantic_annotation_id: UUID
    semantic_region_id: UUID
    semantic_type: str
    target_schema: str
    canonical_target_schema: str | None
    compatibility_mode: str | None
    contract_resolution_reason: str | None
    region_envelope_version: str | None


def load_selected_extraction_tasks_for_annotation(
    *,
    document_id: UUID,
    semantic_annotation_id: UUID,
    plan_id: UUID | None = None,
) -> list[PlannedExtractionTask]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH selected_plan AS (
                  SELECT id, semantic_annotation_id
                  FROM semantic_extraction_plans
                  WHERE document_id = %s
                    AND semantic_annotation_id = %s
                    AND (%s::uuid IS NULL OR id = %s)
                  ORDER BY created_at DESC
                  LIMIT 1
                )
                SELECT
                  task.id AS plan_task_id,
                  task.plan_id,
                  selected_plan.semantic_annotation_id,
                  task.semantic_region_id,
                  task.semantic_type,
                  task.target_schema,
                  task.canonical_target_schema,
                  task.compatibility_mode,
                  task.contract_resolution_reason,
                  task.task_json ->> 'regionEnvelopeVersion' AS region_envelope_version
                FROM semantic_extraction_plan_tasks task
                JOIN selected_plan ON selected_plan.id = task.plan_id
                WHERE task.status = 'selected'
                ORDER BY
                  COALESCE((task.task_json ->> 'ordinal')::integer, 0),
                  task.created_at,
                  task.id
                """,
                (document_id, semantic_annotation_id, plan_id, plan_id),
            )
            rows = cur.fetchall()
    return [
        PlannedExtractionTask(
            plan_id=cast(UUID, row["plan_id"]),
            plan_task_id=cast(UUID, row["plan_task_id"]),
            semantic_annotation_id=cast(UUID, row["semantic_annotation_id"]),
            semantic_region_id=cast(UUID, row["semantic_region_id"]),
            semantic_type=str(row["semantic_type"]),
            target_schema=str(row["target_schema"]),
            canonical_target_schema=(
                str(row["canonical_target_schema"]) if row.get("canonical_target_schema") else None
            ),
            compatibility_mode=(
                str(row["compatibility_mode"]) if row.get("compatibility_mode") else None
            ),
            contract_resolution_reason=(
                str(row["contract_resolution_reason"])
                if row.get("contract_resolution_reason")
                else None
            ),
            region_envelope_version=(
                str(row["region_envelope_version"]) if row.get("region_envelope_version") else None
            ),
        )
        for row in rows
    ]


def persist_extraction_plan_with_cursor(
    cur: Any,
    *,
    document_id: UUID,
    semantic_annotation_id: UUID,
    manifest_result: SemanticAnnotationResult,
    plan: GraniteExtractionPlan,
    run_id: str | None = None,
) -> PersistedExtractionPlan:
    report = plan.to_metadata()
    summary_counts = plan.summary_counts()
    cur.execute(
        """
        INSERT INTO semantic_extraction_plans (
          document_id, semantic_annotation_id, planner_version,
          prompt_version, model_profile, run_id, status, selected_task_count,
          skipped_task_count, abstention_count, missing_contract_count,
          missing_grounding_count, incompatible_schema_count,
          duplicate_suppressed_count, report_json
        )
        VALUES (
          %s, %s, %s, %s, %s, %s, 'planned', %s, %s, %s, %s, %s, %s, %s, %s::jsonb
        )
        RETURNING id
        """,
        (
            document_id,
            semantic_annotation_id,
            PLANNER_VERSION,
            manifest_result.manifest.prompt_version,
            manifest_result.manifest.profile_name,
            run_id,
            summary_counts["selected_task_count"],
            summary_counts["skipped_task_count"],
            summary_counts["abstention_count"],
            summary_counts["missing_contract_count"],
            summary_counts["missing_grounding_count"],
            summary_counts["incompatible_schema_count"],
            summary_counts["duplicate_suppressed_count"],
            Jsonb(report),
        ),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Semantic extraction plan insert failed.")
    plan_id = cast(UUID, row["id"])
    selected_task_ids: dict[UUID, UUID] = {}
    for spec in plan.selected:
        task_id = _insert_plan_task(cur, plan_id=plan_id, spec=spec, status="selected")
        selected_task_ids[spec.region_id] = task_id
    for spec in plan.dropped:
        status, skip_reason = dropped_task_status_and_reason(spec)
        _insert_plan_task(
            cur,
            plan_id=plan_id,
            spec=spec,
            status=status,
            skip_reason=skip_reason,
        )
    return PersistedExtractionPlan(plan_id=plan_id, selected_task_ids=selected_task_ids)


def _insert_plan_task(
    cur: Any,
    *,
    plan_id: UUID,
    spec: GraniteJobSpec,
    status: str,
    skip_reason: str | None = None,
) -> UUID:
    grounding = spec.region.grounding
    task_json = {
        **_spec_json(spec),
        "status": status,
        "skipReason": skip_reason,
    }
    cur.execute(
        """
        INSERT INTO semantic_extraction_plan_tasks (
          plan_id, document_id, semantic_region_id, semantic_type,
          granite_task, extractor_backend, resolved_document_type,
          target_schema, canonical_target_schema, model_output_schema_name,
          contract_resolution_reason, compatibility_mode, grounding_kind,
          page_number, page_id, element_id, table_id, status, skip_reason,
          review_required, task_json
        )
        SELECT
          %s, r.document_id, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
          %s,
          COALESCE(psa.page_number, dp.page_number, dep.page_number, dtp.page_number),
          %s, %s, %s, %s, %s, %s, %s::jsonb
        FROM semantic_region_annotations r
        LEFT JOIN page_semantic_annotations psa ON psa.id = r.page_annotation_id
        LEFT JOIN document_pages dp ON dp.id = r.page_id
        LEFT JOIN document_elements de ON de.id = r.element_id
        LEFT JOIN document_pages dep ON dep.id = de.page_id
        LEFT JOIN document_tables dt ON dt.id = r.table_id
        LEFT JOIN document_pages dtp ON dtp.id = dt.page_id
        WHERE r.id = %s
        RETURNING id
        """,
        (
            plan_id,
            spec.region_id,
            spec.region.semantic_type,
            spec.region.granite_task,
            spec.extractor_backend,
            spec.metadata.get("resolved_document_type"),
            spec.target_schema,
            spec.canonical_target_schema,
            spec.model_output_schema_name,
            spec.contract_resolution_reason,
            spec.compatibility_mode,
            grounding.kind,
            grounding.page_id,
            grounding.element_id,
            grounding.table_id,
            status,
            skip_reason,
            spec.region.review_required or spec.target_schema == "document_observation",
            Jsonb(task_json),
            spec.region_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Semantic extraction plan task insert failed.")
    return cast(UUID, row["id"])


def _spec_json(spec: GraniteJobSpec) -> dict[str, object]:
    return {
        "semanticRegionId": str(spec.region_id),
        "semanticType": spec.region.semantic_type,
        "graniteTask": spec.region.granite_task,
        "targetSchema": spec.target_schema,
        "canonicalTargetSchema": spec.canonical_target_schema,
        "modelOutputSchemaName": spec.model_output_schema_name,
        "contractResolutionReason": spec.contract_resolution_reason,
        "compatibilityMode": spec.compatibility_mode,
        "extractorBackend": spec.extractor_backend,
        "priority": spec.priority,
        "ordinal": spec.ordinal,
        "schemaFit": spec.schema_fit.to_json(),
        "metadata": dict(spec.metadata),
    }
